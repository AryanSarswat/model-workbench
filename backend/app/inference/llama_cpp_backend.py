"""Local GGUF inference via llama-cpp-python -- runs on any hardware (CPU fallback).

The model file stays loaded in a process-wide cache: constructing a fresh Llama per
chat turn would reload multi-GB weights every request, so unlike HFInferenceAPIBackend
(which must be closed per request to release its httpx pool) this backend's aclose()
is a no-op and the instance is reused. Single-user tool, so no eviction -- the most
recently used model simply stays resident.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from llama_cpp import Llama, LlamaGrammar

from app.errors import WorkbenchError
from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage
from app.inference.structured_output import PromptJsonRetrier, ToolCall
from app.tools import ToolSpec, get_tool

_CACHE: dict[str, Llama] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


def _build_grammar(output_schema: dict) -> LlamaGrammar:
    """Compile a JSON Schema to a GBNF grammar. An invalid schema is a 400
    raised pre-stream -- never a mid-stream failure."""
    try:
        return LlamaGrammar.from_json_schema(json.dumps(output_schema))
    except (ValueError, AssertionError, AttributeError, TypeError) as e:
        # JSONDecodeError (a ValueError) for malformed JSON, AssertionError for
        # a well-formed but unrecognized schema; AttributeError/TypeError cover
        # non-object or non-serializable input, which from_json_schema/json
        # reject with those instead.
        raise WorkbenchError(
            400, "invalid_output_schema", f"invalid output_schema: {e}"
        ) from None


class LlamaCppBackend:
    def __init__(self, model_path: str | Path) -> None:
        self._model_path = str(model_path)

    def capabilities(self) -> BackendCapabilities:
        # JSON Schema constrains decoding via GBNF grammar (wired up once structured
        # output lands); chat-template tool calling is natively supported.
        return BackendCapabilities(structured_output_mode="grammar", native_tool_calling=True)

    def _get_llama(self) -> Llama:
        with _CACHE_LOCK:
            llama = _CACHE.get(self._model_path)
            if llama is None:
                llama = Llama(model_path=self._model_path, verbose=False)
                _CACHE[self._model_path] = llama
            return llama

    async def _run_native_tool_loop(
        self,
        llama: Llama,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        grammar: LlamaGrammar | None = None,
    ) -> str:
        """Drive non-streamed chat turns until the model answers without tool calls.

        History is plain dicts (converted once from ChatMessage at entry) so the
        "tool"-role result messages -- which the public ChatMessage schema has no
        variant for -- can ride along. A failing tool yields an "Error: ..." result
        string, never a loop crash. Exhausted turns return the last content seen.
        """
        history: list[dict] = [m.model_dump() for m in messages]
        # OpenAI tool shape -- llama-cpp-python reads tool["function"], so a bare
        # spec dict would KeyError (or be silently filtered) inside the library.
        tool_schemas = [{"type": "function", "function": spec.model_dump()} for spec in tools]
        last_content = ""
        retrier = PromptJsonRetrier()
        for _ in range(5):
            extra_kwargs: dict = {"grammar": grammar} if grammar is not None else {}
            response = await asyncio.to_thread(
                llama.create_chat_completion,
                messages=history,
                tools=tool_schemas,
                tool_choice="auto",
                stream=False,
                **extra_kwargs,
            )
            message = response["choices"][0]["message"]
            if message.get("content"):
                last_content = message["content"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                # Small models (e.g. Qwen2.5-0.5B) emit the tool attempt as plain
                # text (<tool_call>{"name": ..., "arguments": ...}</tool_call>)
                # which llama-cpp-python never parses into message["tool_calls"].
                # Fall back to the shared PromptJsonRetrier parser -- native when
                # the template supports it, prompt-JSON otherwise.
                content = message.get("content") or ""
                parsed = retrier.parse_tool_call_or_reply(content) if content else None
                if not isinstance(parsed, ToolCall):
                    return content
                history.append(dict(message))
                try:
                    result = await get_tool(parsed.tool_name).run(parsed.arguments)
                except WorkbenchError as e:
                    result = f"Error: {e.message}"
                except Exception as e:  # noqa: BLE001 -- a failing tool is loop feedback, not fatal
                    result = f"Error: {e}"
                history.append({"role": "tool", "tool_call_id": "", "content": result})
                continue
            history.append(dict(message))
            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name", "")
                args = function.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = None
                if not isinstance(args, dict):
                    result = f"Error: invalid arguments for tool '{name}': expected a JSON object"
                else:
                    try:
                        result = await get_tool(name).run(args)
                    except WorkbenchError as e:
                        result = f"Error: {e.message}"
                    except Exception as e:  # noqa: BLE001 -- a failing tool is loop feedback, not fatal
                        result = f"Error: {e}"
                history.append(
                    {"role": "tool", "tool_call_id": call.get("id", ""), "content": result}
                )
        return last_content

    async def aclose(self) -> None:
        """No-op -- the cached Llama stays loaded for the next turn. The chat router
        still calls this (it closes whatever backend get_backend() returned), so the
        method exists for Protocol conformance, not because there's anything to free."""

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        # model_id is Protocol compat only -- the registry already bound this backend
        # to a specific local file, so there's nothing left to resolve per request.
        # A schema compiles to a GBNF grammar up front: invalid schemas raise a
        # 400 pre-stream (outside every try below, so the error raises instead
        # of becoming a terminal chunk).
        grammar = _build_grammar(output_schema) if output_schema is not None else None
        if tools:
            # Tools mode runs non-streamed turns and yields the final reply as one
            # delta + done: tool-calling turns can't stream partial tool calls
            # honestly, so nothing streams until the loop resolves to final text.
            # With a schema every native turn is grammar-constrained as well.
            try:
                llama = await asyncio.to_thread(self._get_llama)
            except Exception as e:  # noqa: BLE001 -- same terminal shape as below
                yield ChatChunk(done=True, error=f"failed to load {self._model_path}: {e}")
                return
            try:
                final = await self._run_native_tool_loop(llama, messages, tools, grammar)
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=final)
            yield ChatChunk(done=True)
            return
        try:
            llama = await asyncio.to_thread(self._get_llama)
        except Exception as e:  # noqa: BLE001 -- any load failure becomes a terminal
            # error chunk, never a mid-stream traceback (same contract as HF backend)
            yield ChatChunk(done=True, error=f"failed to load {self._model_path}: {e}")
            return
        try:
            stream_kwargs: dict = {"grammar": grammar} if grammar is not None else {}
            stream = llama.create_chat_completion(
                messages=[m.model_dump() for m in messages],
                stream=True,
                **stream_kwargs,
            )
            if grammar is not None:
                # Constrained turns run to completion: collect the full text,
                # then yield the final JSON as one delta + done.
                parts: list[str] = []
                while True:
                    chunk = await asyncio.to_thread(next, stream, _SENTINEL)
                    if chunk is _SENTINEL:
                        break
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        parts.append(delta)
                yield ChatChunk(delta="".join(parts))
                yield ChatChunk(done=True)
                return
            while True:
                chunk = await asyncio.to_thread(next, stream, _SENTINEL)
                if chunk is _SENTINEL:
                    break
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield ChatChunk(delta=delta)
            yield ChatChunk(done=True)
        except Exception as e:  # noqa: BLE001 -- see above
            yield ChatChunk(done=True, error=str(e))
