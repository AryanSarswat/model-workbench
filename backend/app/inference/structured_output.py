"""Prompt-and-retry JSON fallback for structured output and tool calling.

Backends without grammar/guided decoding instruct the model to reply with exactly
one JSON object, parse it back out of free text, and feed failures into the next
turn. This is the ONE shared JSON-extraction path (see AGENTS.md).
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
    """Reject anything that is not a JSON-serializable dict, as a 400 pre-stream."""
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


def extract_json_object(text: str) -> dict | None:
    """Return the first {...} substring that decodes to a JSON object, or None.

    Models wrap JSON in chatter/tags, so decoding starts at each `{`.
    Never raises on string input.
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
            if isinstance(expected, str):
                names = [expected]
            elif isinstance(expected, list):
                names = expected
            else:
                names = []
            if names and not any(
                _json_type_matches(data[key], name) for name in names if isinstance(name, str)
            ):
                return False
    return True


def is_conforming_json(text: str, schema: dict) -> bool:
    """True when text is exactly one JSON object matching schema -- the tool-loop
    fast path that lets a conforming final draft skip the schema redraft."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return False
    return matches_schema(data, schema)


def _with_instruction(messages: list[ChatMessage], content: str) -> list[ChatMessage]:
    """Insert a system instruction after any leading system message, so a
    caller-supplied persona is never clobbered."""
    instruction = ChatMessage(role="system", content=content)
    if messages and messages[0].role == "system":
        return [messages[0], instruction, *messages[1:]]
    return [instruction, *messages]


class PromptJsonRetrier:
    """Build tool-call prompts and parse free-text model output back into calls."""

    def build_tool_messages(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        output_schema: dict | None = None,
    ) -> list[ChatMessage]:
        """Prefix messages with a system instruction describing the JSON protocol.

        With output_schema the instruction also requires the FINAL reply to
        conform to it, so every loop turn already knows the target shape.
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
        return _with_instruction(messages, "\n".join(lines))

    def build_schema_messages(
        self, messages: list[ChatMessage], schema: dict
    ) -> list[ChatMessage]:
        """Prefix messages with a system instruction describing the JSON schema."""
        return _with_instruction(
            messages,
            "Reply with exactly one JSON object and nothing else.\n"
            "The object must conform to this JSON Schema:\n" + json.dumps(schema),
        )

    def parse_tool_call_or_reply(self, text: str) -> ToolCall | TextReply | None:
        """Extract the first {...} JSON object from free text (models add chatter).

        Never raises on model output -- unparseable text or a JSON object that is
        neither a tool call nor a reply yields None so the caller can retry with
        error feedback.
        """
        try:
            obj = extract_json_object(text)
        except (TypeError, ValueError):
            # Non-string input -- just means "retry".
            return None
        if obj is None:
            return None
        if isinstance(obj.get("tool"), str) and isinstance(obj.get("arguments"), dict):
            return ToolCall(tool_name=obj["tool"], arguments=obj["arguments"])
        # Qwen-style dialect: <tool_call>{"name": ..., "arguments": ...}</tool_call>
        # (the {...} scan already strips the tags).
        if isinstance(obj.get("name"), str) and isinstance(obj.get("arguments"), dict):
            return ToolCall(tool_name=obj["name"], arguments=obj["arguments"])
        if isinstance(obj.get("reply"), str):
            return TextReply(text=obj["reply"])
        return None

    def parse_schema_reply(self, text: str) -> dict | TextReply | None:
        """Extract the single JSON object of a schema-constrained turn.

        Dict on success; TextReply when the model sent prose with no JSON at all;
        None when JSON was attempted but unparseable (or input is not a string).
        """
        try:
            obj = extract_json_object(text)
        except (TypeError, ValueError):
            return None
        if obj is not None:
            return obj
        if isinstance(text, str) and "{" not in text:
            return TextReply(text=text)
        return None
