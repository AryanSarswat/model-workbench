"""Remote inference via the HF Inference API -- the only backend that needs nothing
downloaded locally. Which model_ids actually work depends on HF routing the request to a
provider that serves it; an unsupported model_id is a normal BadRequestError, not a bug.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HTTPError

from app.inference.schemas import (
    BackendCapabilities,
    ChatChunk,
    ChatMessage,
    TokenUsage,
    combine_usage,
)
from app.inference.structured_output import (
    PromptJsonRetrier,
    is_conforming_json,
    matches_schema,
    validate_output_schema,
)
from app.inference.tool_loop import LoopResult, run_tool_loop
from app.tools import ToolSpec

_SCHEMA_RETRY_MESSAGE = (
    "That was not valid JSON conforming to the required schema. "
    "Reply with exactly one JSON object and nothing else."
)


class HFInferenceAPIBackend:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncInferenceClient(token=api_key)

    def capabilities(self) -> BackendCapabilities:
        # A remote provider offers no grammar/guided decoding control.
        return BackendCapabilities(structured_output_mode="prompt_retry", native_tool_calling=False)

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Shared dict/serializable check only: the retry loop has no
        generator-time schema rejection to mirror."""
        validate_output_schema(schema)

    async def aclose(self) -> None:
        """Callers must close each instance or its httpx pool leaks."""
        await self._client.close()

    async def _generate_text(
        self, model_id: str, messages: list[ChatMessage]
    ) -> tuple[str, TokenUsage | None]:
        """One non-streamed turn for the tool/schema loops; errors propagate to
        stream_chat, which reports them as a terminal chunk."""
        completion = await self._client.chat_completion(
            messages=[m.model_dump() for m in messages],
            model=model_id,
            stream=False,
        )
        text = completion.choices[0].message.content or ""
        usage = None
        if completion.usage is not None:
            usage = TokenUsage(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
            )
        return text, usage

    async def _run_schema_loop(
        self,
        generate: Callable[[list[ChatMessage]], Awaitable[str]],
        messages: list[ChatMessage],
        schema: dict,
        max_iterations: int = 5,
    ) -> tuple[str, int]:
        """Best-effort schema turns: at most max_iterations, each failure fed back
        as a user-role message.

        Returns (text, retries), retries being the 0-indexed attempt that
        succeeded. Exhausted turns return the last raw text with
        retries == max_iterations - 1; never raises for schema reasons.
        """
        retrier = PromptJsonRetrier()
        history = retrier.build_schema_messages(messages, schema)
        last_text = ""
        for attempt in range(max_iterations):
            last_text = await generate(history)
            parsed = retrier.parse_schema_reply(last_text)
            history.append(ChatMessage(role="assistant", content=last_text))
            if isinstance(parsed, dict) and matches_schema(parsed, schema):
                return json.dumps(parsed), attempt
            history.append(ChatMessage(role="user", content=_SCHEMA_RETRY_MESSAGE))
        return last_text, max_iterations - 1

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        if output_schema is not None:
            # Outside every try so an invalid schema raises (400).
            validate_output_schema(output_schema)
        if tools or output_schema is not None:
            # Tool and schema turns are non-streamed (retries can't stream partial
            # output honestly); the final reply yields as one delta + done.
            usages: list[TokenUsage] = []
            loop_result = LoopResult(text="")
            retries = 0

            async def _generate(history: list[ChatMessage]) -> str:
                text, usage = await self._generate_text(model_id, history)
                if usage is not None:
                    usages.append(usage)
                return text

            try:
                final = ""
                history = messages
                if tools:
                    # The tool loop runs first; its reply is assistant context for
                    # any schema turns that follow.
                    prompt_messages = PromptJsonRetrier().build_tool_messages(
                        messages, tools, output_schema
                    )
                    loop_result = await run_tool_loop(_generate, prompt_messages, tools)
                    final = loop_result.text
                    history = [*messages, ChatMessage(role="assistant", content=final)]
                # Without tools final is "", which never conforms.
                if output_schema is not None and not is_conforming_json(final, output_schema):
                    final, retries = await self._run_schema_loop(
                        _generate, history, output_schema
                    )
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=final)
            yield ChatChunk(
                done=True,
                usage=combine_usage(usages),
                tools_called=loop_result.tools_called,
                tool_calls=loop_result.tool_calls,
                retries=retries,
            )
            return
        try:
            stream = await self._client.chat_completion(
                messages=[m.model_dump() for m in messages],
                model=model_id,
                stream=True,
                stream_options={"include_usage": True},
            )
            usage: TokenUsage | None = None
            async for completion_chunk in stream:
                # The terminal usage-only chunk (stream_options.include_usage)
                # carries empty choices -- indexing [0] on it would raise.
                if completion_chunk.choices:
                    delta = completion_chunk.choices[0].delta.content
                    if delta:
                        yield ChatChunk(delta=delta)
                if completion_chunk.usage is not None:
                    usage = TokenUsage(
                        prompt_tokens=completion_chunk.usage.prompt_tokens,
                        completion_tokens=completion_chunk.usage.completion_tokens,
                    )
            yield ChatChunk(done=True, usage=usage)
        except HTTPError as e:
            yield ChatChunk(done=True, error=str(e))
