"""Remote inference via the HF Inference API -- the only backend that needs nothing
downloaded locally. Which model_ids actually work depends on HF routing the request to a
provider that serves it; an unsupported model_id is a normal BadRequestError, not a bug.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HTTPError

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage
from app.inference.structured_output import (
    PromptJsonRetrier,
    matches_schema,
    validate_output_schema,
)
from app.inference.tool_loop import run_tool_loop
from app.tools import ToolSpec

_SCHEMA_RETRY_MESSAGE = (
    "That was not valid JSON conforming to the required schema. "
    "Reply with exactly one JSON object and nothing else."
)


class HFInferenceAPIBackend:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncInferenceClient(token=api_key)

    def capabilities(self) -> BackendCapabilities:
        # No grammar/guided decoding control over a remote provider -- structured output
        # and tool calling both go through the prompt-and-retry fallback for this backend.
        return BackendCapabilities(structured_output_mode="prompt_retry", native_tool_calling=False)

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Shared dict/serializable check only (the Protocol default).

        The prompt-and-retry schema loop never raises for schema reasons -- it
        returns the last text when turns run out -- so there is no
        generator-time rejection path to mirror here.
        """
        validate_output_schema(schema)

    async def aclose(self) -> None:
        """A fresh backend (and its underlying httpx connection pool) is created per
        request in the chat router -- callers must close it or the pool leaks."""
        await self._client.close()

    async def _generate_text(self, model_id: str, messages: list[ChatMessage]) -> str:
        """One non-streamed model turn for the fallback tool loop. HTTPError (and any
        other failure) propagates to the tools branch of stream_chat, which reports
        it as a terminal error chunk -- the same treatment as the streaming path."""
        completion = await self._client.chat_completion(
            messages=[m.model_dump() for m in messages],
            model=model_id,
            stream=False,
        )
        return completion.choices[0].message.content or ""

    async def _run_schema_loop(
        self,
        generate: Callable[[list[ChatMessage]], Awaitable[str]],
        messages: list[ChatMessage],
        schema: dict,
        max_iterations: int = 5,
    ) -> str:
        """Best-effort schema-constrained turns over the shared prompt-and-retry
        helpers, mirroring run_tool_loop's shape: at most max_iterations model
        turns, each failure fed back as a user-role message.

        Success returns the parsed object re-serialized, so the delta is pure
        JSON. Exhausted turns return the last raw text -- the caller still
        emits a terminal chunk, never raises.
        """
        retrier = PromptJsonRetrier()
        history = retrier.build_schema_messages(messages, schema)
        last_text = ""
        for _ in range(max_iterations):
            last_text = await generate(history)
            parsed = retrier.parse_schema_reply(last_text)
            history.append(ChatMessage(role="assistant", content=last_text))
            if isinstance(parsed, dict) and matches_schema(parsed, schema):
                return json.dumps(parsed)
            history.append(ChatMessage(role="user", content=_SCHEMA_RETRY_MESSAGE))
        return last_text

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        if output_schema is not None:
            # Pre-stream 400 -- outside the try below so an invalid schema
            # raises instead of becoming a terminal chunk.
            validate_output_schema(output_schema)
        if tools or output_schema is not None:
            # Constrained/tool turns run non-streamed and yield the final reply
            # as one delta + done: neither tool-calling nor retry turns can
            # stream partial output honestly, so nothing streams until the loop
            # resolves to final text.
            try:
                async def _generate(history: list[ChatMessage]) -> str:
                    return await self._generate_text(model_id, history)

                if tools:
                    # The tool loop runs first; its tool-informed final reply
                    # then enters the schema-constrained turn(s) as assistant
                    # context (tool traffic stays in messages).
                    prompt_messages = PromptJsonRetrier().build_tool_messages(
                        messages, tools
                    )
                    tool_final = await run_tool_loop(_generate, prompt_messages, tools)
                    history = [
                        *messages,
                        ChatMessage(role="assistant", content=tool_final),
                    ]
                else:
                    history = messages
                if output_schema is not None:
                    final = await self._run_schema_loop(
                        _generate, history, output_schema
                    )
                else:
                    # Tools-only: output_schema is None implies tools is set,
                    # so tool_final is bound (outer condition guarantees one).
                    final = tool_final
            except HTTPError as e:
                yield ChatChunk(done=True, error=str(e))
                return
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=final)
            yield ChatChunk(done=True)
            return
        try:
            stream = await self._client.chat_completion(
                messages=[m.model_dump() for m in messages],
                model=model_id,
                stream=True,
            )
            async for completion_chunk in stream:
                delta = completion_chunk.choices[0].delta.content
                if delta:
                    yield ChatChunk(delta=delta)
            yield ChatChunk(done=True)
        except HTTPError as e:
            yield ChatChunk(done=True, error=str(e))
