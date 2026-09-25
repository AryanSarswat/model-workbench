"""File-backed test-case dataset, per docs/architecture.md's data model.

One file per case (`{id}.json` under `data/test_cases/`) -- diffable, no merge
conflicts, category filtering by scan. `TestCase` + `load_cases()` are the seam the
eval engine will import; the HTTP layer in `router.py` is a thin wrapper over this
module and adds nothing the eval PR needs to know about.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import get_settings
from app.errors import WorkbenchError
from app.inference.schemas import ChatMessage

# URL-safe only: ids double as filenames (`{id}.json`) and path params, so anything
# outside this set is rejected (also blocks `../` escapes in raw path params).
_ID_PATTERN = r"^[A-Za-z0-9._-]+"
_ID_RE = re.compile(_ID_PATTERN + "$")


AssertionType = Literal[
    "schema_valid",
    "contains",
    "regex",
    "tool_called",
    "structured_output_first_try",
    "native_tool_calling",
    "json_parse_success",
]


class Assertion(BaseModel):
    type: AssertionType
    value: str | None = None  # "contains"
    pattern: str | None = None  # "regex"
    name: str | None = None  # "tool_called"


class TestCaseJudge(BaseModel):
    criteria: str


class TestCase(BaseModel):
    """Mirrors data/test_cases.template.json. Only id/category/messages are required."""

    id: str = Field(pattern=_ID_PATTERN)
    category: str  # free-form, not an enum -- new categories need no code change
    messages: list[ChatMessage]
    system_prompt: str | None = None
    output_schema: dict[str, Any] | None = None
    expected_tools: list[str] | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    judge: TestCaseJudge | None = None
    tags: list[str] = Field(default_factory=list)


def get_cases_dir() -> Path:
    """Dataset location: `Settings.test_cases_dir` (env `TEST_CASES_DIR`) or the default."""
    override = get_settings().test_cases_dir
    if override is not None:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data" / "test_cases"


def load_cases(category: str | None = None) -> list[TestCase]:
    """Eval-engine seam: all cases (or one category), sorted by id. Missing dir reads as empty."""
    cases_dir = get_cases_dir()
    if not cases_dir.is_dir():
        return []
    cases = [
        TestCase.model_validate_json(path.read_text())
        for path in sorted(cases_dir.glob("*.json"))
    ]
    if category is not None:
        cases = [case for case in cases if case.category == category]
    return cases


def get_case(case_id: str) -> TestCase:
    path = _case_path(case_id)
    if not path.is_file():
        raise WorkbenchError(
            status_code=404,
            code="test_case_not_found",
            message=f"No test case with id {case_id!r}.",
        )
    return TestCase.model_validate_json(path.read_text())


def create_case(case: TestCase) -> TestCase:
    path = _case_path(case.id)
    if path.exists():
        raise WorkbenchError(
            status_code=409,
            code="test_case_already_exists",
            message=f"Test case with id {case.id!r} already exists.",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(case.model_dump_json(indent=2) + "\n")
    return case


def update_case(case_id: str, case: TestCase) -> TestCase:
    if case.id != case_id:
        raise WorkbenchError(
            status_code=422,
            code="test_case_id_mismatch",
            message=f"Path id {case_id!r} does not match body id {case.id!r}.",
        )
    path = _case_path(case_id)
    if not path.is_file():
        raise WorkbenchError(
            status_code=404,
            code="test_case_not_found",
            message=f"No test case with id {case_id!r}.",
        )
    path.write_text(case.model_dump_json(indent=2) + "\n")
    return case


def delete_case(case_id: str) -> None:
    path = _case_path(case_id)
    if not path.is_file():
        raise WorkbenchError(
            status_code=404,
            code="test_case_not_found",
            message=f"No test case with id {case_id!r}.",
        )
    path.unlink()


def _case_path(case_id: str) -> Path:
    if not _ID_RE.match(case_id):
        raise WorkbenchError(
            status_code=422,
            code="invalid_test_case_id",
            message=f"Test case id {case_id!r} is not URL-safe (allowed: letters, digits, . _ -).",
        )
    return get_cases_dir() / f"{case_id}.json"
