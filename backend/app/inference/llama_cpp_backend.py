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
from app.inference.schemas import (
    BackendCapabilities,
    ChatChunk,
    ChatMessage,
    TokenUsage,
    combine_usage,
)
from app.inference.structured_output import (
    PromptJsonRetrier,
    ToolCall,
    validate_output_schema,
)
from app.inference.tool_loop import LoopResult
from app.tools import ToolSpec, get_tool

_CACHE: dict[str, Llama] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


def _parse_usage(usage_dict: dict | None) -> TokenUsage | None:
    if not usage_dict:
        return None
    return TokenUsage(
        prompt_tokens=usage_dict["prompt_tokens"],
        completion_tokens=usage_dict["completion_tokens"],
    )


def _estimate_streaming_usage(
    llama: Llama, messages: list[ChatMessage], completion_text: str
) -> TokenUsage | None:
    """Approximate usage for the plain streaming path, whose chunks carry no usage.

    Prompt tokens count a newline-joined transcript, not the exact chat-template
    rendering (not exposed by llama-cpp-python) -- fine for relative tokens/sec.
    Returns None rather than failing a turn that already streamed.
    """
    try:
        prompt_text = "\n".join(m.content for m in messages)
        prompt_tokens = len(llama.tokenize(prompt_text.encode("utf-8")))
        completion_tokens = len(llama.tokenize(completion_text.encode("utf-8"), add_bos=False))
    except Exception:  # noqa: BLE001 -- see above
        return None
    return TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


async def _run_tool(name: str, args: dict, tools_called: list[str]) -> str:
    """Execute one tool call; an unknown or failing tool becomes an "Error: ..."
    result for the model, never a loop crash. Only resolved tools are recorded."""
    try:
        tool = get_tool(name)
    except WorkbenchError as e:
        return f"Error: {e.message}"
    try:
        result = await tool.run(args)
    except Exception as e:  # noqa: BLE001 -- a failing tool is loop feedback, not fatal
        result = f"Error: {e}"
    tools_called.append(name)
    return result


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
        return BackendCapabilities(structured_output_mode="grammar", native_tool_calling=True)

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Same grammar compile the generator runs, but pre-stream and model-free.

        from_json_schema touches no weights, so compiling here turns a
        dict-shaped-but-invalid schema (e.g. {"type": 42}) into a 400 before
        StreamingResponse starts instead of a mid-stream failure.
        """
        validate_output_schema(schema)
        _build_grammar(schema)

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
    ) -> tuple[LoopResult, TokenUsage | None]:
        """Drive non-streamed chat turns until the model answers without tool calls.

        History is plain dicts so "tool"-role result messages, which ChatMessage
        has no variant for, can ride along. Exhausted turns return the last
        content seen.
        """
        history: list[dict] = [m.model_dump() for m in messages]
        # OpenAI tool shape -- llama-cpp-python reads tool["function"], so a bare
        # spec dict would KeyError (or be silently filtered) inside the library.
        tool_schemas = [{"type": "function", "function": spec.model_dump()} for spec in tools]
        last_content = ""
        tools_called: list[str] = []
        usages: list[TokenUsage] = []
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
            usage = _parse_usage(response.get("usage"))
            if usage is not None:
                usages.append(usage)
            message = response["choices"][0]["message"]
            if message.get("content"):
                last_content = message["content"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                # Small models (e.g. Qwen2.5-0.5B) emit the tool call as plain-text
                # <tool_call>{...}</tool_call>, which llama-cpp-python never parses
                # into message["tool_calls"]; fall back to the shared parser.
                content = message.get("content") or ""
                parsed = retrier.parse_tool_call_or_reply(content) if content else None
                if not isinstance(parsed, ToolCall):
                    return LoopResult(text=content, tools_called=tools_called), combine_usage(
                        usages
                    )
                history.append(dict(message))
                result = await _run_tool(parsed.tool_name, parsed.arguments, tools_called)
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
                if isinstance(args, dict):
                    result = await _run_tool(name, args, tools_called)
                else:
                    result = f"Error: invalid arguments for tool '{name}': expected a JSON object"
                history.append(
                    {"role": "tool", "tool_call_id": call.get("id", ""), "content": result}
                )
        return LoopResult(text=last_content, tools_called=tools_called), combine_usage(usages)

    async def aclose(self) -> None:
        """No-op: the cached Llama stays loaded for the next turn."""

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        # model_id is unused: the registry already bound this backend to one file.
        # The grammar compiles outside every try so an invalid schema raises (400)
        # instead of becoming a terminal chunk.
        grammar = _build_grammar(output_schema) if output_schema is not None else None
        try:
            llama = await asyncio.to_thread(self._get_llama)
        except Exception as e:  # noqa: BLE001 -- a load failure is a terminal chunk
            yield ChatChunk(done=True, error=f"failed to load {self._model_path}: {e}")
            return
        if tools:
            # Tool turns are non-streamed; the final reply yields as one delta + done.
            # With a schema every native turn is grammar-constrained as well.
            try:
                loop_result, usage = await self._run_native_tool_loop(
                    llama, messages, tools, grammar
                )
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=loop_result.text)
            yield ChatChunk(done=True, usage=usage, tools_called=loop_result.tools_called)
            return
        try:
            if grammar is not None:
                # Constrained turns never stream; a non-streamed call also returns
                # llama.cpp's exact usage.
                response = await asyncio.to_thread(
                    llama.create_chat_completion,
                    messages=[m.model_dump() for m in messages],
                    grammar=grammar,
                    stream=False,
                )
                final_text = response["choices"][0]["message"]["content"] or ""
                yield ChatChunk(delta=final_text)
                yield ChatChunk(done=True, usage=_parse_usage(response.get("usage")))
                return
            stream = llama.create_chat_completion(
                messages=[m.model_dump() for m in messages],
                stream=True,
            )
            parts: list[str] = []
            while True:
                chunk = await asyncio.to_thread(next, stream, _SENTINEL)
                if chunk is _SENTINEL:
                    break
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    parts.append(delta)
                    yield ChatChunk(delta=delta)
            completion_text = "".join(parts)
            yield ChatChunk(
                done=True, usage=_estimate_streaming_usage(llama, messages, completion_text)
            )
        except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
            yield ChatChunk(done=True, error=str(e))
