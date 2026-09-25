"""Local transformers inference from a downloaded snapshot -- fallback for models
without a GGUF build (MPS/CUDA/CPU auto-detected).

Same lifecycle shape as LlamaCppBackend: the snapshot stays loaded in a process-wide
cache (reloading weights every turn would be multi-GB per request), so aclose() is a
no-op for Protocol conformance. Single-user tool, so no eviction -- the most recently
used snapshot simply stays resident.

Generation runs until the model's EOS token -- no token cap. trust_remote_code stays
off: a snapshot is an arbitrary user-chosen repo, and loading it must never execute
repo-shipped code; models that need custom code surface a terminal load error instead.

Constrained (output_schema) turns never stream: outlines guided decoding biases the
whole turn's logits, so those turns run to completion (max_new_tokens=512, the same
cap as tool-loop turns) and yield the final JSON as one delta + done.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    LogitsProcessorList,
    TextIteratorStreamer,
)

from app.errors import WorkbenchError
from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage, TokenUsage
from app.inference.structured_output import PromptJsonRetrier, matches_schema
from app.inference.tool_loop import LoopResult, run_tool_loop
from app.tools import ToolSpec

try:
    # Sibling-owned schema validator (structured-output worker). Tolerated, not
    # reimplemented: if their commit is ever absent from this branch, outlines
    # itself still rejects bad schemas at processor-build time, wrapped to the
    # same 400 below.
    from app.inference.structured_output import validate_output_schema
except ImportError:
    validate_output_schema = None  # type: ignore[assignment]

_CACHE: dict[str, tuple[AutoModelForCausalLM, AutoTokenizer]] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


def _detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _combine_usage(usages: list[TokenUsage]) -> TokenUsage | None:
    """completion_tokens sums across turns; prompt_tokens takes the last turn's
    figure (it already includes every prior turn's history)."""
    if not usages:
        return None
    return TokenUsage(
        prompt_tokens=usages[-1].prompt_tokens,
        completion_tokens=sum(u.completion_tokens for u in usages),
    )


def _build_guided_processor(
    model: AutoModelForCausalLM, tokenizer: AutoTokenizer, output_schema: dict
):
    """One fresh outlines-guided LogitsProcessor for a single generate call.

    Built per turn, never shared: the outlines-core processor carries
    per-sequence guide state, so reuse across turns would leak FSM state
    between generations. Outlines is imported lazily so this module stays
    importable without the `local` extra (registry._require_local precedent).
    """
    try:
        import outlines
        from outlines.backends import get_json_schema_logits_processor
    except ImportError as e:
        raise WorkbenchError(
            400,
            "backend_not_available",
            "Structured output needs outlines -- run 'cd backend && uv sync --extra local'.",
        ) from e
    try:
        guided_model = outlines.from_transformers(model, tokenizer)
        return get_json_schema_logits_processor(
            None, guided_model, json.dumps(output_schema)
        )
    except WorkbenchError:
        raise
    except Exception as e:
        # The schema is the only caller-controlled input here, so any build
        # failure -- outlines' ValueError/TypeError schema rejections above all --
        # is reported as an invalid schema.
        raise WorkbenchError(
            400, "invalid_output_schema", f"invalid output_schema: {e}"
        ) from e


class TransformersBackend:
    def __init__(self, snapshot_dir: str | Path) -> None:
        self._snapshot_dir = str(snapshot_dir)
        self._device = _detect_device()

    def capabilities(self) -> BackendCapabilities:
        # outlines guided decoding + native chat-template tool calling (both wired up
        # once structured output / tool calling land).
        return BackendCapabilities(structured_output_mode="guided", native_tool_calling=True)

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Reject a bad schema pre-stream without loading the model.

        The default outlines-core backend builds its guide from the schema
        string alone (build_regex_from_schema), so running that same function
        here exercises the exact rejection path _build_guided_processor hits --
        anything it rejects would also fail at generator time, so valid schemas
        can never be over-restricted. Without outlines installed there is
        nothing model-free to probe; the shared dict check runs and the
        generator-time wrapping stays the backstop.
        """
        if validate_output_schema is not None:
            validate_output_schema(schema)
        try:
            from outlines_core.json_schema import build_regex_from_schema
        except ImportError:
            return
        try:
            build_regex_from_schema(json.dumps(schema))
        except Exception as e:
            raise WorkbenchError(
                400, "invalid_output_schema", f"invalid output_schema: {e}"
            ) from e

    def _get_model(self) -> tuple[AutoModelForCausalLM, AutoTokenizer]:
        with _CACHE_LOCK:
            cached = _CACHE.get(self._snapshot_dir)
            if cached is None:
                tokenizer = AutoTokenizer.from_pretrained(self._snapshot_dir)
                model = AutoModelForCausalLM.from_pretrained(
                    self._snapshot_dir,
                    torch_dtype=torch.float16 if self._device != "cpu" else torch.float32,
                    trust_remote_code=False,
                ).to(self._device)
                model.eval()
                cached = (model, tokenizer)
                _CACHE[self._snapshot_dir] = cached
            return cached

    async def aclose(self) -> None:
        """No-op -- the cached model stays loaded for the next turn. The chat router
        still calls this (it closes whatever backend get_backend() returned), so the
        method exists for Protocol conformance, not because there's anything to free."""

    async def _generate_turn(
        self,
        model: AutoModelForCausalLM,
        tokenizer: AutoTokenizer,
        conversation: str,
        output_schema: dict | None = None,
    ) -> tuple[str, TokenUsage]:
        """One non-streamed turn off the accumulated conversation text."""
        inputs = await asyncio.to_thread(tokenizer, conversation, return_tensors="pt")
        inputs = inputs.to(self._device)
        input_len = len(inputs["input_ids"][0])
        # Bound loop turns so short tool-call JSON can't truncate mid-object:
        # generate() defaults to input + 20 tokens, which cuts off arguments.
        # Guided decoding constrains validity, not length, so guided turns
        # share the same cap.
        generate_kwargs = {**inputs, "max_new_tokens": 512}
        if output_schema is not None:
            processor = await asyncio.to_thread(
                _build_guided_processor, model, tokenizer, output_schema
            )
            generate_kwargs["logits_processor"] = LogitsProcessorList([processor])
        outputs = await asyncio.to_thread(model.generate, **generate_kwargs)
        completion_ids = outputs[0][input_len:]
        text = tokenizer.decode(completion_ids, skip_special_tokens=True)
        usage = TokenUsage(prompt_tokens=input_len, completion_tokens=len(completion_ids))
        return text, usage

    async def _run_fallback_tool_loop(
        self,
        model: AutoModelForCausalLM,
        tokenizer: AutoTokenizer,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        output_schema: dict | None = None,
    ) -> tuple[LoopResult, TokenUsage | None]:
        """Drive the shared prompt-and-retry tool loop with non-streamed generation.

        The full prompt text is built ONCE via the chat template; each loop turn
        then appends prior turns and tool results as plain text blocks instead of
        re-applying the template, which would re-render generation prompts
        mid-conversation. Blocking generate calls run on worker threads.

        With output_schema the loop's turns stay unconstrained (they must emit
        tool-call JSON, which the schema must not forbid) and only the final
        reply turn is schema-guided, with every tool result already in context.
        Usage from every generate() call (loop turns and, if it runs, the final
        guided turn) is combined into one figure for the caller.
        """
        prompt_messages = PromptJsonRetrier().build_tool_messages(
            messages, tools, output_schema
        )
        conversation = await asyncio.to_thread(
            tokenizer.apply_chat_template,
            [m.model_dump() for m in prompt_messages],
            add_generation_prompt=True,
            tokenize=False,
        )
        # The template render above already contains every message in history's
        # initial state (prompt_messages), so only later loop turns get appended.
        rendered = len(prompt_messages)
        usages: list[TokenUsage] = []

        async def _generate(history: list[ChatMessage]) -> str:
            nonlocal conversation, rendered
            for message in history[rendered:]:
                conversation += f"\n{message.role}: {message.content}\n"
            rendered = len(history)
            text, usage = await self._generate_turn(model, tokenizer, conversation)
            usages.append(usage)
            return text

        loop_result = await run_tool_loop(_generate, prompt_messages, tools)
        if output_schema is not None:
            # Optimistic fast path: the schema instruction rides every loop
            # turn, so a draft that already conforms skips the guided redraft.
            try:
                draft = json.loads(loop_result.text)
            except (TypeError, ValueError):
                draft = None
            if isinstance(draft, dict) and matches_schema(draft, output_schema):
                return loop_result, _combine_usage(usages)
            final_text, final_usage = await self._generate_turn(
                model, tokenizer, conversation, output_schema
            )
            usages.append(final_usage)
            return (
                LoopResult(text=final_text, tools_called=loop_result.tools_called),
                _combine_usage(usages),
            )
        return loop_result, _combine_usage(usages)

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        # model_id is Protocol compat only -- the registry already bound this backend
        # to a specific snapshot dir, so there's nothing left to resolve per request.
        # An invalid schema raises pre-stream (outside every try below, so the
        # error raises instead of becoming a terminal chunk).
        if output_schema is not None and validate_output_schema is not None:
            validate_output_schema(output_schema)
        try:
            model, tokenizer = await asyncio.to_thread(self._get_model)
        except Exception as e:  # noqa: BLE001 -- any load failure becomes a terminal
            # error chunk, never a mid-stream traceback (same contract as other backends)
            yield ChatChunk(done=True, error=f"failed to load {self._snapshot_dir}: {e}")
            return
        if tools:
            # Tools mode runs non-streamed turns and yields the final reply as one
            # delta + done: tool-calling turns can't stream partial tool calls
            # honestly, so nothing streams until the loop resolves to final text.
            try:
                loop_result, usage = await self._run_fallback_tool_loop(
                    model, tokenizer, messages, tools, output_schema
                )
            except WorkbenchError:
                # Guided setup failures (bad schema, missing outlines) raise
                # pre-stream; everything else is a terminal chunk, never raised.
                raise
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=loop_result.text)
            yield ChatChunk(done=True, usage=usage, tools_called=loop_result.tools_called)
            return
        if output_schema is not None:
            # Constrained turns run to completion under the schema guide, then
            # yield the final JSON as one delta + done: guided turns never
            # stream. The processor builds before the try so a bad schema
            # raises instead of becoming a terminal chunk.
            processor = await asyncio.to_thread(
                _build_guided_processor, model, tokenizer, output_schema
            )
            try:
                inputs = tokenizer.apply_chat_template(
                    [m.model_dump() for m in messages],
                    add_generation_prompt=True,
                    return_tensors="pt",
                    return_dict=True,
                ).to(self._device)
                input_len = len(inputs["input_ids"][0])
                outputs = await asyncio.to_thread(
                    model.generate,
                    **inputs,
                    max_new_tokens=512,
                    logits_processor=LogitsProcessorList([processor]),
                )
                completion_ids = outputs[0][input_len:]
                final = tokenizer.decode(completion_ids, skip_special_tokens=True)
                usage = TokenUsage(
                    prompt_tokens=input_len, completion_tokens=len(completion_ids)
                )
            except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
                yield ChatChunk(done=True, error=str(e))
                return
            yield ChatChunk(delta=final)
            yield ChatChunk(done=True, usage=usage)
            return
        try:
            inputs = tokenizer.apply_chat_template(
                [m.model_dump() for m in messages],
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            ).to(self._device)
            input_len = len(inputs["input_ids"][0])
            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
            # generate() runs on a worker thread while this coroutine drains the
            # streamer. A generate crash must still terminate the stream (never hang
            # the SSE connection), so the wrapper always signals the streamer end and
            # the original error is reported after the drain.
            errors: list[Exception] = []

            def _generate() -> None:
                try:
                    model.generate(**inputs, streamer=streamer)
                except Exception as e:  # noqa: BLE001 -- captured, reported below
                    errors.append(e)
                finally:
                    streamer.end()

            thread = threading.Thread(target=_generate, daemon=True)
            thread.start()
            parts: list[str] = []
            while True:
                text = await asyncio.to_thread(next, streamer, _SENTINEL)
                if text is _SENTINEL:
                    break
                if text:
                    parts.append(text)
                    yield ChatChunk(delta=text)
            await asyncio.to_thread(thread.join)
            if errors:
                yield ChatChunk(done=True, error=str(errors[0]))
            else:
                completion_text = "".join(parts)
                completion_tokens = 0
                if completion_text:
                    encoded = await asyncio.to_thread(
                        tokenizer, completion_text, add_special_tokens=False
                    )
                    completion_tokens = len(encoded["input_ids"])
                yield ChatChunk(
                    done=True,
                    usage=TokenUsage(prompt_tokens=input_len, completion_tokens=completion_tokens),
                )
        except Exception as e:  # noqa: BLE001 -- see above
            yield ChatChunk(done=True, error=str(e))
