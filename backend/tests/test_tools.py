import pytest

from app.errors import WorkbenchError
from app.tools import get_tool, list_tools, reload_tools, resolve_tool_names


async def _run(name: str, args: dict) -> str:
    return await get_tool(name).run(args)


def test_calculator_evaluates_arithmetic():
    import asyncio

    assert asyncio.run(_run("calculator", {"expression": "2 + 3 * 4"})) == "14"
    assert asyncio.run(_run("calculator", {"expression": "(2 + 3) * 4"})) == "20"
    assert asyncio.run(_run("calculator", {"expression": "2 ** 8 + 7 // 2"})) == "259"


def test_calculator_applies_unary_minus():
    import asyncio

    assert asyncio.run(_run("calculator", {"expression": "-5"})) == "-5"
    assert asyncio.run(_run("calculator", {"expression": "2 - -3"})) == "5"


def test_calculator_errors_never_raise():
    import asyncio

    for bad in ["1/0", "__import__('os')", "open('x')", "2 +", "", "abc"]:
        result = asyncio.run(_run("calculator", {"expression": bad}))
        assert result.startswith("Error: "), bad


def test_web_fetch_reads_file_url(tmp_path):
    import asyncio

    target = tmp_path / "page.txt"
    target.write_text("hello from disk")
    result = asyncio.run(_run("web_fetch", {"url": target.as_uri()}))
    assert result == "hello from disk"


def test_web_fetch_rejects_unsupported_scheme():
    import asyncio

    result = asyncio.run(_run("web_fetch", {"url": "gopher://example.com/x"}))
    assert result.startswith("Error: ")


def test_registry_list_get_resolve():
    assert {tool.spec.name for tool in list_tools()} == {"calculator", "web_fetch"}
    assert get_tool("calculator").spec.name == "calculator"
    assert resolve_tool_names(None) == []
    assert resolve_tool_names([]) == []
    assert [t.spec.name for t in resolve_tool_names(["web_fetch"])] == ["web_fetch"]
    with pytest.raises(WorkbenchError) as exc_info:
        get_tool("nope")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "unknown_tool"


def test_reload_tools_keeps_registry_working():
    reload_tools()
    assert {tool.spec.name for tool in list_tools()} == {"calculator", "web_fetch"}
