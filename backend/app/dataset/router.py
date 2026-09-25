"""GET/POST/PUT/DELETE /dataset/cases -- test-case CRUD over the file-backed store.

Thin wrapper over app.dataset.store: ids come from the POST body, single-case
routes address /dataset/cases/{id}, and the collection route filters by ?category=.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dataset.store import TestCase, create_case, delete_case, get_case, load_cases, update_case

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("/cases")
def list_cases(category: str | None = None) -> list[TestCase]:
    return load_cases(category)


@router.post("/cases", status_code=201)
def create_test_case(case: TestCase) -> TestCase:
    return create_case(case)


@router.get("/cases/{case_id}")
def get_test_case(case_id: str) -> TestCase:
    return get_case(case_id)


@router.put("/cases/{case_id}")
def update_test_case(case_id: str, case: TestCase) -> TestCase:
    return update_case(case_id, case)


@router.delete("/cases/{case_id}", status_code=204)
def delete_test_case(case_id: str) -> None:
    delete_case(case_id)
