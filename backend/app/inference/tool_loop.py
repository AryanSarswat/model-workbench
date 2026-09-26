"""Tool-calling loop for backends without native tool support.

The caller supplies `generate`, one non-streamed model turn, so any backend can
drive it. Tool traffic rides as user-role messages so roles stay
system|user|assistant.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.errors import WorkbenchError
from app.inference.schemas import ChatMessage, ToolCallRecord
from app.inference.structured_output import PromptJsonRetrier, TextReply
from app.tools import Tool, ToolSpec, get_tool

_RETRY_MESSAGE = (
    "That was not valid JSON. Reply with exactly one JSON object: "
    '\'{"tool": "<name>", "arguments": {...}}\' to call a tool or '
    '\'{"reply": "<final answer>"}\' for the final answer.'
)


class LoopResult(BaseModel):
    text: str
    # Every tool actually executed, in call order (repeats included).
    tool_calls: list[ToolCallRecord] = []

    @property
    def tools_called(self) -> list[str]:
        return [call.name for call in self.tool_calls]


async def run_tool(tool: Tool, args: dict) -> ToolCallRecord:
    """Execute one resolved tool call; a raising tool becomes an "Error: ..." result
    for the model, never a loop crash."""
    started = time.monotonic()
    try:
        result = await tool.run(args)
    except Exception as exc:  # noqa: BLE001 -- a failing tool is loop feedback, not fatal
        result = f"Error: {exc}"
    return ToolCallRecord(
        name=tool.spec.name,
        arguments=args,
        result=result,
        duration_ms=(time.monotonic() - started) * 1000,
    )


async def run_tool_loop(
    generate: Callable[[list[ChatMessage]], Awaitable[str]],
    messages: list[ChatMessage],
    tools: list[ToolSpec],
    max_iterations: int = 5,
) -> LoopResult:
    """Run up to max_iterations model turns until a final reply, else return the
    last raw text. Tool results, unknown-tool errors, and JSON retries are fed
    back as user-role messages; a raising tool yields an "Error: ..." result.

    `messages` must already carry the tool instruction from
    PromptJsonRetrier.build_tool_messages (the transformers backend renders its
    prompt from the same list, so building it here would duplicate it).
    """
    retrier = PromptJsonRetrier()
    history = list(messages)
    last_text = ""
    tool_calls: list[ToolCallRecord] = []
    for _ in range(max_iterations):
        last_text = await generate(history)
        parsed = retrier.parse_tool_call_or_reply(last_text)
        history.append(ChatMessage(role="assistant", content=last_text))
        if isinstance(parsed, TextReply):
            return LoopResult(text=last_text, tool_calls=tool_calls)
        if parsed is None:
            history.append(ChatMessage(role="user", content=_RETRY_MESSAGE))
            continue
        try:
            tool = get_tool(parsed.tool_name)
        except WorkbenchError:
            history.append(
                ChatMessage(
                    role="user",
                    content=(
                        f"Tool '{parsed.tool_name}' is not available. Reply with "
                        "exactly one JSON object using an available tool or a "
                        '{"reply": ...} object.'
                    ),
                )
            )
            continue
        call = await run_tool(tool, parsed.arguments)
        tool_calls.append(call)
        history.append(
            ChatMessage(
                role="user", content=f"Tool '{parsed.tool_name}' returned: {call.result}"
            )
        )
    return LoopResult(text=last_text, tool_calls=tool_calls)
