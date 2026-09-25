"""Local transformers inference from a downloaded snapshot -- fallback for models
without a GGUF build (MPS/CUDA/CPU auto-detected).

Same lifecycle as LlamaCppBackend: loaded snapshots stay in a process-wide cache with
no eviction, so aclose() is a no-op.

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
    validate_output_schema,
)
from app.inference.tool_loop import LoopResult, run_tool_loop
from app.tools import ToolSpec

_CACHE: dict[str, tuple[AutoModelForCausalLM, AutoTokenizer]] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


def _detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


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
        return BackendCapabilities(structured_output_mode="guided", native_tool_calling=True)

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Reject a bad schema pre-stream without loading the model.

        outlines-core builds its guide from the schema string alone, so
        build_regex_from_schema hits the same rejection path as
        _build_guided_processor. Without outlines there is nothing model-free to
        probe; the generator-time check stays the backstop.
        """
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
        """No-op: the cached model stays loaded for the next turn."""

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
        # generate() defaults to input + 20 tokens, which truncates tool-call JSON.
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

        The chat template renders the prompt ONCE; later turns and tool results
        are appended as plain text, since re-applying the template would re-render
        generation prompts mid-conversation.

        With output_schema the loop turns stay unconstrained (they must emit
        tool-call JSON the schema would forbid) and only a final redraft is
        schema-guided.
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
        # The schema instruction rides every loop turn, so a conforming draft
        # skips the guided redraft.
        if output_schema is not None and not is_conforming_json(
            loop_result.text, output_schema
        ):
            final_text, final_usage = await self._generate_turn(
                model, tokenizer, conversation, output_schema
            )
            usages.append(final_usage)
            return (
                LoopResult(text=final_text, tools_called=loop_result.tools_called),
                combine_usage(usages),
            )
        return loop_result, combine_usage(usages)

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]:
        # model_id is unused: the registry already bound this backend to one
        # snapshot. Schema errors raise (400) outside every try below instead of
        # becoming a terminal chunk.
        if output_schema is not None:
            validate_output_schema(output_schema)
        try:
            model, tokenizer = await asyncio.to_thread(self._get_model)
        except Exception as e:  # noqa: BLE001 -- a load failure is a terminal chunk
            yield ChatChunk(done=True, error=f"failed to load {self._snapshot_dir}: {e}")
            return
        if tools:
            # Tool turns are non-streamed; the final reply yields as one delta + done.
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
            # Guided turns never stream. The processor builds before the try so
            # a bad schema raises instead of becoming a terminal chunk.
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
            # streamer; the wrapper always ends the streamer so a crash can't hang
            # the stream, and the error is reported after the drain.
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
        except Exception as e:  # noqa: BLE001 -- failures are a terminal chunk, never raised
            yield ChatChunk(done=True, error=str(e))
