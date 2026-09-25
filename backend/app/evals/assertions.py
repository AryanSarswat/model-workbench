"""Runs a test case's assertions against one eval turn's response. None needs a
second model call; that is judge.py's job."""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.dataset.store import Assertion, AssertionType, TestCase
from app.errors import WorkbenchError
from app.inference.schemas import BackendCapabilities
from app.inference.structured_output import extract_json_object, matches_schema


class AssertionResult(BaseModel):
    type: AssertionType
    passed: bool
    detail: str = ""


def run_assertions(
    case: TestCase,
    response: str,
    capabilities: BackendCapabilities,
    tools_called: list[str],
    retries: int,
) -> list[AssertionResult]:
    return [
        _run_one(assertion, case, response, capabilities, tools_called, retries)
        for assertion in case.assertions
    ]


def _run_one(
    assertion: Assertion,
    case: TestCase,
    response: str,
    capabilities: BackendCapabilities,
    tools_called: list[str],
    retries: int,
) -> AssertionResult:
    if assertion.type == "schema_valid":
        parsed = extract_json_object(response)
        if case.output_schema is None:
            # An authoring bug (the case never set output_schema), not a model
            # failure -- worth distinguishing so a reviewer doesn't chase the
            # model's response when the test case itself is misconfigured.
            return AssertionResult(
                type=assertion.type, passed=False, detail="case has no output_schema set"
            )
        if parsed is None:
            return AssertionResult(
                type=assertion.type, passed=False, detail="no JSON object found in response"
            )
        passed = matches_schema(parsed, case.output_schema)
        detail = "" if passed else "response did not match output_schema"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "contains":
        passed = assertion.value is not None and assertion.value in response
        detail = "" if passed else f"'{assertion.value}' not found in response"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "regex":
        passed = (
            assertion.pattern is not None and re.search(assertion.pattern, response) is not None
        )
        detail = "" if passed else f"pattern '{assertion.pattern}' did not match"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "tool_called":
        passed = assertion.name is not None and assertion.name in tools_called
        detail = "" if passed else f"tool '{assertion.name}' was never called"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "structured_output_first_try":
        passed = retries == 0
        detail = "" if passed else f"took {retries} retries"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "native_tool_calling":
        passed = capabilities.native_tool_calling
        detail = "" if passed else "backend has no native tool calling"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    if assertion.type == "json_parse_success":
        passed = extract_json_object(response) is not None
        detail = "" if passed else "no JSON object found in response"
        return AssertionResult(type=assertion.type, passed=passed, detail=detail)
    raise WorkbenchError(
        400, "unsupported_assertion", f"Unknown assertion type: {assertion.type}"
    )
