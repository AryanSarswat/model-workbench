"""Prompt-and-retry JSON fallback for structured output and tool calling.

Remote backends (HF Inference API) offer no grammar- or guided-decoding support,
so machine-readable output is secured the only remaining way: instruct the model
to reply with exactly one JSON object, parse it back out of free text, and on
failure feed the error into the next turn. This module is the ONE shared fallback
mechanism -- per AGENTS.md nothing tool-specific may build a second
JSON-extraction path; backends with native tool calling never touch this module.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from app.inference.schemas import ChatMessage
from app.tools import ToolSpec


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict


class TextReply(BaseModel):
    text: str


class PromptJsonRetrier:
    """Build tool-call prompts and parse free-text model output back into calls."""

    def build_tool_messages(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> list[ChatMessage]:
        """Prefix messages with a system instruction describing the JSON protocol.

        An existing leading system message is kept first; the tool instruction is
        inserted after it so a caller-supplied persona is never clobbered.
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
        instruction = ChatMessage(role="system", content="\n".join(lines))
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
            decoder = json.JSONDecoder()
            for start, char in enumerate(text):
                if char != "{":
                    continue
                try:
                    obj, _ = decoder.raw_decode(text[start:])
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if isinstance(obj.get("tool"), str) and isinstance(
                    obj.get("arguments"), dict
                ):
                    return ToolCall(tool_name=obj["tool"], arguments=obj["arguments"])
                if isinstance(obj.get("reply"), str):
                    return TextReply(text=obj["reply"])
                return None
        except (TypeError, ValueError):
            # Non-string input, malformed JSON (JSONDecodeError), or pydantic
            # validation failure (ValidationError) -- all just mean "retry".
            return None
        return None
