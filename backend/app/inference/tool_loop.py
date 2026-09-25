"""Agentic tool-calling loop for backends without native tool support.

Why this exists: backends like the HF Inference API cannot enforce a tool schema,
so multi-step tool use runs on the shared PromptJsonRetrier fallback instead --
parse each turn, execute, feed the result back, retry on malformed output. The
loop is backend-agnostic: the caller supplies `generate`, one non-streamed model
turn, so any backend can drive it. Tool traffic rides as user-role messages
(roles stay system|user|assistant) so every backend's model_dump() keeps working.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.errors import WorkbenchError
from app.inference.schemas import ChatMessage
from app.inference.structured_output import PromptJsonRetrier, TextReply
from app.tools import ToolSpec, get_tool

_RETRY_MESSAGE = (
    "That was not valid JSON. Reply with exactly one JSON object: "
    '\'{"tool": "<name>", "arguments": {...}}\' to call a tool or '
    '\'{"reply": "<final answer>"}\' for the final answer.'
)


class LoopResult(BaseModel):
    text: str
    # Every tool name actually executed, in call order (a tool called twice
    # appears twice) -- feeds the eval engine's tool_called assertion.
    tools_called: list[str] = []


async def run_tool_loop(
    generate: Callable[[list[ChatMessage]], Awaitable[str]],
    messages: list[ChatMessage],
    tools: list[ToolSpec],
    max_iterations: int = 5,
) -> LoopResult:
    """Run model turns until a final reply, or return the last raw text.

    Each iteration is one model turn (max_iterations counts model turns, not tool
    executions). Tool results, unknown-tool errors, and JSON retries are appended
    as user-role messages so the model sees the feedback on the next turn. A
    tool whose run() raises unexpectedly yields an "Error: ..." result instead
    of crashing the loop.

    `messages` must already carry the tool instruction -- callers build it once
    with PromptJsonRetrier.build_tool_messages (the transformers backend renders
    its one-time chat-template prompt from the same list, so building here too
    would prefix the instruction twice).
    """
    retrier = PromptJsonRetrier()
    history = list(messages)
    last_text = ""
    tools_called: list[str] = []
    for _ in range(max_iterations):
        last_text = await generate(history)
        parsed = retrier.parse_tool_call_or_reply(last_text)
        history.append(ChatMessage(role="assistant", content=last_text))
        if isinstance(parsed, TextReply):
            return LoopResult(text=last_text, tools_called=tools_called)
        if parsed is None or not isinstance(parsed.arguments, dict):
            history.append(ChatMessage(role="user", content=_RETRY_MESSAGE))
            continue
        try:
            tool = get_tool(parsed.tool_name)
        except WorkbenchError:
            tool = None
        if tool is None:
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
        try:
            result = await tool.run(parsed.arguments)
        except Exception as exc:  # noqa: BLE001 -- a failing tool is loop feedback, not fatal
            result = f"Error: {exc}"
        tools_called.append(parsed.tool_name)
        history.append(
            ChatMessage(
                role="user", content=f"Tool '{parsed.tool_name}' returned: {result}"
            )
        )
    return LoopResult(text=last_text, tools_called=tools_called)
