"""Focused tests for the shared PromptJsonRetrier fallback."""

from app.inference.schemas import ChatMessage
from app.inference.structured_output import PromptJsonRetrier, TextReply, ToolCall
from app.tools import ToolSpec


def _spec() -> ToolSpec:
    return ToolSpec(
        name="calculator",
        description="Evaluate arithmetic.",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
    )


def test_build_tool_messages_prepends_instruction_without_system():
    result = PromptJsonRetrier().build_tool_messages(
        [ChatMessage(role="user", content="hi")], [_spec()]
    )

    assert result[0].role == "system"
    assert "calculator" in result[0].content
    assert "Evaluate arithmetic." in result[0].content
    assert "expression" in result[0].content
    assert [m.content for m in result[1:]] == ["hi"]


def test_build_tool_messages_keeps_existing_system_first():
    messages = [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="hi"),
    ]

    result = PromptJsonRetrier().build_tool_messages(messages, [_spec()])

    assert [m.role for m in result] == ["system", "system", "user"]
    assert result[0].content == "Be concise."
    assert "calculator" in result[1].content
    assert result[2].content == "hi"


def test_parse_tool_call_with_surrounding_chatter():
    parsed = PromptJsonRetrier().parse_tool_call_or_reply(
        'Sure, computing that: {"tool": "calculator", '
        '"arguments": {"expression": "2+3"}} done'
    )

    assert parsed == ToolCall(tool_name="calculator", arguments={"expression": "2+3"})


def test_parse_reply():
    assert PromptJsonRetrier().parse_tool_call_or_reply('{"reply": "The answer is 5"}') == (
        TextReply(text="The answer is 5")
    )


def test_parse_garbage_returns_none():
    retrier = PromptJsonRetrier()

    assert retrier.parse_tool_call_or_reply("no json here at all") is None
    assert retrier.parse_tool_call_or_reply("{oops, not json") is None


def test_parse_tool_call_with_missing_keys_returns_none():
    retrier = PromptJsonRetrier()

    assert retrier.parse_tool_call_or_reply('{"tool": "calculator"}') is None
    assert retrier.parse_tool_call_or_reply('{"arguments": {"expression": "2"}}') is None


def test_parse_tool_call_with_name_key_and_tool_call_tags():
    parsed = PromptJsonRetrier().parse_tool_call_or_reply(
        '<tool_call>\n{"name": "calculator", "arguments": {"expression": "2+3"}}\n</tool_call>'
    )

    assert parsed == ToolCall(tool_name="calculator", arguments={"expression": "2+3"})


def test_parse_tool_call_with_name_key_and_surrounding_chatter():
    parsed = PromptJsonRetrier().parse_tool_call_or_reply(
        'Sure, computing that: <tool_call>{"name": "calculator", '
        '"arguments": {"expression": "2+3"}}</tool_call> done'
    )

    assert parsed == ToolCall(tool_name="calculator", arguments={"expression": "2+3"})
