"""Remote inference via the HF Inference API -- the only backend that needs nothing
downloaded locally. Which model_ids actually work depends on HF routing the request to a
provider that serves it; an unsupported model_id is a normal BadRequestError, not a bug.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HTTPError

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage
from app.inference.structured_output import PromptJsonRetrier
from app.inference.tool_loop import run_tool_loop
from app.tools import ToolSpec


class HFInferenceAPIBackend:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncInferenceClient(token=api_key)

    def capabilities(self) -> BackendCapabilities:
        # No grammar/guided decoding control over a remote provider -- structured output
        # and tool calling both go through the prompt-and-retry fallback for this backend.
        return BackendCapabilities(structured_output_mode="prompt_retry", native_tool_calling=False)

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

    async def stream_chat(
        self, model_id: str, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> AsyncIterator[ChatChunk]:
        if tools:
            # Tools mode runs non-streamed turns and yields the final reply as one
            # delta + done: tool-calling turns can't stream partial tool calls
            # honestly, so nothing streams until the loop resolves to final text.
            try:
                prompt_messages = PromptJsonRetrier().build_tool_messages(messages, tools)

                async def _generate(history: list[ChatMessage]) -> str:
                    return await self._generate_text(model_id, history)

                final = await run_tool_loop(_generate, prompt_messages, tools)
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
