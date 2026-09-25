"""LLM-as-judge scoring for test cases that carry a judge.criteria rubric. Runs on
the same backend type as the eval run (there is no separate judge-backend field).
"""

from __future__ import annotations

from app.dataset.store import TestCase
from app.errors import WorkbenchError
from app.inference.registry import get_backend
from app.inference.schemas import ChatMessage
from app.inference.structured_output import extract_json_object

_JUDGE_PROMPT_TEMPLATE = (
    "Score the following response from 0 to 1 based on this criteria: {criteria}\n\n"
    "Response:\n{response}\n\n"
    'Reply with exactly one JSON object: {{"score": <number between 0 and 1>, '
    '"rationale": "<one sentence why>"}}.'
)


async def score_with_judge(
    backend_name: str,
    judge_model_id: str,
    hf_api_key: str | None,
    case: TestCase,
    response: str,
) -> tuple[float, str]:
    """Returns (score, rationale). A judge reply that isn't parseable JSON with a
    numeric score scores 0.0 with a rationale explaining why -- never raises,
    since one bad judge turn shouldn't fail the whole eval run.
    """
    if case.judge is None:
        raise WorkbenchError(
            400, "no_judge_criteria", f"Test case {case.id} has no judge.criteria."
        )
    backend = get_backend(backend_name, judge_model_id, hf_api_key)
    prompt = _JUDGE_PROMPT_TEMPLATE.format(criteria=case.judge.criteria, response=response)
    try:
        parts: list[str] = []
        async for chunk in backend.stream_chat(
            judge_model_id, [ChatMessage(role="user", content=prompt)]
        ):
            if chunk.error is not None:
                return 0.0, f"Judge call failed: {chunk.error}"
            parts.append(chunk.delta)
    finally:
        await backend.aclose()
    text = "".join(parts)
    parsed = extract_json_object(text)
    score_value = parsed.get("score") if isinstance(parsed, dict) else None
    # bool is not a number here even though it subclasses int in Python -- same
    # convention as structured_output.py's _json_type_matches.
    if not isinstance(score_value, (int, float)) or isinstance(score_value, bool):
        return 0.0, "Judge response was not valid JSON with a numeric score."
    score = max(0.0, min(1.0, float(parsed["score"])))
    rationale = str(parsed.get("rationale", ""))
    return score, rationale
