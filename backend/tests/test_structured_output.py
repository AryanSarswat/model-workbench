"""Focused tests for the shared PromptJsonRetrier fallback."""

import json

import pytest

from app.errors import WorkbenchError
from app.inference.schemas import ChatMessage
from app.inference.structured_output import (
    PromptJsonRetrier,
    TextReply,
    ToolCall,
    extract_json_object,
    matches_schema,
    validate_output_schema,
)
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


def test_build_tool_messages_with_schema_embeds_instruction_and_schema():
    result = PromptJsonRetrier().build_tool_messages(
        [ChatMessage(role="user", content="hi")], [_spec()], _schema()
    )

    assert result[0].role == "system"
    assert json.dumps(_schema()) in result[0].content
    assert "FINAL reply" in result[0].content
    assert '{"tool":' in result[0].content
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


def _schema() -> dict:
    return {
        "type": "object",
        "required": ["name", "age"],
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    }


def test_validate_output_schema_accepts_serializable_dict():
    validate_output_schema(_schema())  # must not raise


def test_validate_output_schema_rejects_non_dict():
    for bad in ("just a string", ["a", "list"], None, 42):
        with pytest.raises(WorkbenchError) as exc_info:
            validate_output_schema(bad)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_output_schema"


def test_validate_output_schema_rejects_non_serializable():
    with pytest.raises(WorkbenchError) as exc_info:
        validate_output_schema({"callback": object()})

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_output_schema"


def test_build_schema_messages_embeds_schema_and_keeps_system_first():
    messages = [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="Your name?"),
    ]

    result = PromptJsonRetrier().build_schema_messages(messages, _schema())

    assert [m.role for m in result] == ["system", "system", "user"]
    assert result[0].content == "Be concise."
    assert json.dumps(_schema()) in result[1].content
    assert result[2].content == "Your name?"


def test_schema_build_parse_round_trip_valid_first_try():
    retrier = PromptJsonRetrier()
    messages = retrier.build_schema_messages(
        [ChatMessage(role="user", content="Your name?")], _schema()
    )

    assert messages[0].role == "system"

    parsed = retrier.parse_schema_reply('{"name": "Ada", "age": 36}')

    assert parsed == {"name": "Ada", "age": 36}
    assert matches_schema(parsed, _schema()) is True


def test_parse_schema_reply_garbage_then_valid_retry_shape():
    retrier = PromptJsonRetrier()

    first = retrier.parse_schema_reply("Let me think about this...")
    assert isinstance(first, TextReply)

    assert retrier.parse_schema_reply('{"name": ') is None

    assert retrier.parse_schema_reply('Sure: {"name": "Ada", "age": 36}') == {
        "name": "Ada",
        "age": 36,
    }


def test_matches_schema_accepts_valid_and_rejects_mismatches():
    assert matches_schema({"name": "Ada", "age": 36}, _schema()) is True
    assert matches_schema({"name": "Ada"}, _schema()) is False
    assert matches_schema({"name": "Ada", "age": "36"}, _schema()) is False
    assert matches_schema({"name": "Ada", "age": True}, _schema()) is False


def test_extract_json_object_finds_a_json_object_wrapped_in_chatter():
    assert extract_json_object('Sure: {"answer": 42} thanks') == {"answer": 42}


def test_extract_json_object_returns_none_for_no_json():
    assert extract_json_object("no json here") is None
