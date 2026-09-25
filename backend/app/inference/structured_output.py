"""Prompt-and-retry JSON fallback for structured output and tool calling.

Remote backends (HF Inference API) offer no grammar- or guided-decoding support,
so machine-readable output is secured the only remaining way: instruct the model
to reply with exactly one JSON object, parse it back out of free text, and on
failure feed the error into the next turn. This module is the ONE shared fallback
mechanism -- per AGENTS.md nothing tool-specific may build a second
JSON-extraction path; backends with native tool calling never touch this module.
Schema-constrained turns share the same {...} scanner via parse_schema_reply.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from app.errors import WorkbenchError
from app.inference.schemas import ChatMessage
from app.tools import ToolSpec


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict


class TextReply(BaseModel):
    text: str


def validate_output_schema(schema: object) -> None:
    """Reject anything that is not a JSON-serializable dict, pre-stream.

    Same bucket as unknown_tool: callers validate before the first model turn
    so a bad schema is a 400, never a mid-stream failure.
    """
    if not isinstance(schema, dict):
        raise WorkbenchError(
            400,
            "invalid_output_schema",
            f"output_schema must be a JSON object, got {type(schema).__name__}",
        )
    try:
        json.dumps(schema)
    except (TypeError, ValueError) as exc:
        raise WorkbenchError(
            400, "invalid_output_schema", f"output_schema must be JSON-serializable: {exc}"
        ) from None


def _extract_first_json_dict(text: str) -> dict | None:
    """Return the first {...} substring that decodes to a JSON object.

    Models wrap JSON in chatter/tags, so decoding starts at each `{`.
    Returns None when nothing decodes. Never raises on string input.
    """
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def extract_json_object(text: str) -> dict | None:
    """Public entry point to the {...} scanner above, for eval assertions
    (schema_valid, json_parse_success) that need the same lenient extraction the
    retry loops use internally -- a model can wrap JSON in chatter even on a
    constrained turn."""
    return _extract_first_json_dict(text)


def _json_type_matches(value: object, type_name: str) -> bool:
    """Check one JSON Schema type name without coercion (bool is not integer)."""
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "null":
        return value is None
    return True  # Unknown type keyword: permissive, never reject.


def matches_schema(data: dict, schema: dict) -> bool:
    """Minimal structural check of parsed output against the schema, no jsonschema dep.

    Only required-key presence and per-property `type` checks (no coercion).
    Extra keys and unknown keywords are allowed -- this is a retry signal for
    the schema loop, not a validator for user input.
    """
    if not isinstance(data, dict) or not isinstance(schema, dict):
        return False
    required = schema.get("required")
    if isinstance(required, list) and not all(key in data for key in required):
        return False
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, prop in properties.items():
            if key not in data or not isinstance(prop, dict):
                continue
            expected = prop.get("type")
            if expected is None:
                continue
            names = (
                [expected]
                if isinstance(expected, str)
                else (expected if isinstance(expected, list) else [])
            )
            if names and not any(
                _json_type_matches(data[key], name) for name in names if isinstance(name, str)
            ):
                return False
    return True


class PromptJsonRetrier:
    """Build tool-call prompts and parse free-text model output back into calls."""

    def build_tool_messages(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        output_schema: dict | None = None,
    ) -> list[ChatMessage]:
        """Prefix messages with a system instruction describing the JSON protocol.

        An existing leading system message is kept first; the tool instruction is
        inserted after it so a caller-supplied persona is never clobbered. With
        output_schema the instruction additionally requires the FINAL reply to
        conform to the schema, so every loop turn already knows the target shape.
        None (the default) leaves the prompt byte-identical to the tools-only form.
        """
        lines = [
            "Reply with exactly one JSON object per turn and nothing else.",
            'To call a tool, reply {"tool": "<name>", "arguments": {...}}.',
            'When you have the final answer, reply {"reply": "<final answer>"}.',
            "",
            "Available tools:",
        ]
        for tool in tools:
            lines.append(
                f"- {tool.name}: {tool.description} "
                f"Parameters: {json.dumps(tool.parameters)}"
            )
        if output_schema is not None:
            lines.extend(
                [
                    "",
                    (
                        'Tool calls use {"tool": ...} as above, but the FINAL reply must '
                        "be exactly one JSON object conforming to this JSON Schema:"
                    ),
                    json.dumps(output_schema),
                ]
            )
        instruction = ChatMessage(role="system", content="\n".join(lines))
        if messages and messages[0].role == "system":
            return [messages[0], instruction, *messages[1:]]
        return [instruction, *messages]

    def build_schema_messages(
        self, messages: list[ChatMessage], schema: dict
    ) -> list[ChatMessage]:
        """Prefix messages with a system instruction describing the JSON schema.

        An existing leading system message is kept first; the schema instruction
        is inserted after it so a caller-supplied persona is never clobbered.
        """
        instruction = ChatMessage(
            role="system",
            content=(
                "Reply with exactly one JSON object and nothing else.\n"
                "The object must conform to this JSON Schema:\n" + json.dumps(schema)
            ),
        )
        if messages and messages[0].role == "system":
            return [messages[0], instruction, *messages[1:]]
        return [instruction, *messages]

    def parse_tool_call_or_reply(self, text: str) -> ToolCall | TextReply | None:
        """Extract the first {...} JSON object from free text (models add chatter).

        Never raises on model output -- unparseable text or a JSON object that is
        neither a tool call nor a reply yields None so the caller can retry with
        error feedback.
        """
        try:
            obj = _extract_first_json_dict(text)
        except (TypeError, ValueError):
            # Non-string input -- just means "retry".
            return None
        if obj is None:
            return None
        try:
            if isinstance(obj.get("tool"), str) and isinstance(obj.get("arguments"), dict):
                return ToolCall(tool_name=obj["tool"], arguments=obj["arguments"])
            # Qwen-style dialect: <tool_call>{"name": ..., "arguments": ...}</tool_call>.
            # The {...} scan above already strips the surrounding tags/chatter, so
            # only the `name` key shape needs handling here.
            if isinstance(obj.get("name"), str) and isinstance(obj.get("arguments"), dict):
                return ToolCall(tool_name=obj["name"], arguments=obj["arguments"])
            if isinstance(obj.get("reply"), str):
                return TextReply(text=obj["reply"])
            return None
        except (TypeError, ValueError):
            # Malformed JSON (JSONDecodeError) or pydantic validation failure
            # (ValidationError) -- all just mean "retry".
            return None

    def parse_schema_reply(self, text: str) -> dict | TextReply | None:
        """Extract the single JSON object of a schema-constrained turn.

        Shares the {...} scanner above -- no second extraction path. Dict on
        success; TextReply when the model sent prose with no JSON at all; None
        when JSON was attempted but unparseable (or input is not a string), so
        the caller can retry with error feedback.
        """
        try:
            obj = _extract_first_json_dict(text)
        except (TypeError, ValueError):
            return None
        if obj is not None:
            return obj
        if isinstance(text, str) and "{" not in text:
            return TextReply(text=text)
        return None
