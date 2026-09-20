import pytest

from app.dataset.store import Assertion, TestCase
from app.errors import WorkbenchError
from app.evals.assertions import run_assertions
from app.inference.schemas import BackendCapabilities, ChatMessage


def _case(**overrides) -> TestCase:
    defaults = dict(
        id="case-1",
        category="general",
        messages=[ChatMessage(role="user", content="hi")],
        assertions=[],
    )
    defaults.update(overrides)
    return TestCase(**defaults)


def _capabilities(native_tool_calling: bool) -> BackendCapabilities:
    return BackendCapabilities(
        structured_output_mode="grammar", native_tool_calling=native_tool_calling
    )


def test_contains_assertion_passes_when_value_is_present():
    case = _case(assertions=[Assertion(type="contains", value="hello")])

    results = run_assertions(case, "hello world", _capabilities(False), [], 0)

    assert results[0].passed is True


def test_contains_assertion_fails_when_value_is_absent():
    case = _case(assertions=[Assertion(type="contains", value="hello")])

    results = run_assertions(case, "goodbye", _capabilities(False), [], 0)

    assert results[0].passed is False


def test_regex_assertion_matches_pattern():
    case = _case(assertions=[Assertion(type="regex", pattern=r"\d+ sentences?")])

    results = run_assertions(case, "here are 3 sentences", _capabilities(False), [], 0)

    assert results[0].passed is True


def test_schema_valid_assertion_checks_extracted_json_against_the_case_schema():
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    case = _case(output_schema=schema, assertions=[Assertion(type="schema_valid")])

    results = run_assertions(case, '{"answer": 42}', _capabilities(False), [], 0)

    assert results[0].passed is True


def test_schema_valid_assertion_fails_on_mismatched_type():
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    case = _case(output_schema=schema, assertions=[Assertion(type="schema_valid")])

    results = run_assertions(case, '{"answer": "not a number"}', _capabilities(False), [], 0)

    assert results[0].passed is False


def test_tool_called_assertion_checks_the_tools_called_list():
    case = _case(assertions=[Assertion(type="tool_called", name="calculator")])

    passing = run_assertions(case, "5", _capabilities(False), ["calculator"], 0)
    failing = run_assertions(case, "5", _capabilities(False), [], 0)

    assert passing[0].passed is True
    assert failing[0].passed is False


def test_structured_output_first_try_assertion_checks_retries():
    case = _case(assertions=[Assertion(type="structured_output_first_try")])

    first_try = run_assertions(case, "{}", _capabilities(False), [], 0)
    retried = run_assertions(case, "{}", _capabilities(False), [], 2)

    assert first_try[0].passed is True
    assert retried[0].passed is False


def test_native_tool_calling_assertion_reads_backend_capabilities():
    case = _case(assertions=[Assertion(type="native_tool_calling")])

    native = run_assertions(case, "5", _capabilities(True), [], 0)
    fallback = run_assertions(case, "5", _capabilities(False), [], 0)

    assert native[0].passed is True
    assert fallback[0].passed is False


def test_json_parse_success_assertion_detects_valid_json_anywhere_in_the_response():
    case = _case(assertions=[Assertion(type="json_parse_success")])

    results = run_assertions(case, 'Sure: {"a": 1} thanks', _capabilities(False), [], 0)

    assert results[0].passed is True


def test_json_parse_success_assertion_fails_on_no_json():
    case = _case(assertions=[Assertion(type="json_parse_success")])

    results = run_assertions(case, "no json here", _capabilities(False), [], 0)

    assert results[0].passed is False


def test_unsupported_assertion_type_raises_workbench_error():
    case = _case(assertions=[Assertion(type="contains", value="x")])
    case.assertions[0].type = "not_a_real_type"  # bypass Literal validation for this test

    with pytest.raises(WorkbenchError) as exc_info:
        run_assertions(case, "x", _capabilities(False), [], 0)

    assert exc_info.value.code == "unsupported_assertion"
