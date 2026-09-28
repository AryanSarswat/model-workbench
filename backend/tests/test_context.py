"""The context report behind the Playground's context meter: every message the model
was given, labelled by where it came from, so the meter can show what fills the window."""

from app.inference.context import build_context_report
from app.inference.schemas import ChatMessage


def _words(text: str) -> int:
    return len(text.split())


def test_labels_each_message_by_where_it_came_from():
    request = [
        ChatMessage(role="system", content="Be brief."),
        ChatMessage(role="user", content="What is 2 + 3?"),
    ]
    sent = [
        {"role": "system", "content": "Be brief."},
        {"role": "system", "content": "Reply with exactly one JSON object per turn."},
        {"role": "user", "content": "What is 2 + 3?"},
        {"role": "assistant", "content": '{"tool": "calculator", "arguments": {}}'},
        {"role": "user", "content": "Tool 'calculator' returned: 5"},
        {"role": "user", "content": "That was not valid JSON."},
    ]

    report = build_context_report(request, _words, window=32768, sent=sent)

    # The workbench's own additions (tool protocol, retry feedback) are told apart
    # from the caller's messages, and tool results from user text.
    assert [m.kind for m in report.messages] == [
        "system",
        "instructions",
        "user",
        "assistant",
        "tool",
        "instructions",
    ]
    assert [m.tokens for m in report.messages] == [2, 8, 5, 4, 4, 5]
    assert report.window == 32768


def test_native_tool_messages_and_calls_are_shown():
    # llama.cpp's native loop: results ride a "tool" role, and an assistant turn
    # that only calls a tool has no content -- its calls are what it said.
    request = [ChatMessage(role="user", content="What is 2 + 3?")]
    call = {"function": {"name": "calculator", "arguments": '{"expression": "2 + 3"}'}}
    sent = [
        {"role": "user", "content": "What is 2 + 3?"},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "", "content": "5"},
    ]

    report = build_context_report(request, _words, window=8192, sent=sent)

    assert [m.kind for m in report.messages] == ["user", "assistant", "tool"]
    assert "calculator" in report.messages[1].content


def test_without_a_tokenizer_messages_have_no_token_counts():
    request = [ChatMessage(role="user", content="hi")]

    report = build_context_report(request, None, window=None)

    assert report.messages[0].tokens is None
    assert report.window is None
