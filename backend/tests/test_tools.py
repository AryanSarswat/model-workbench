import asyncio
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.errors import WorkbenchError
from app.tools import get_tool, list_tools, reload_tools, resolve_tool_names


async def _run(name: str, args: dict) -> str:
    return await get_tool(name).run(args)


@contextmanager
def _serve_html_once(html: str):
    """A local http server that answers one GET with `html`; yields its URL."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.server_close()


def test_calculator_evaluates_arithmetic():
    assert asyncio.run(_run("calculator", {"expression": "2 + 3 * 4"})) == "14"
    assert asyncio.run(_run("calculator", {"expression": "(2 + 3) * 4"})) == "20"
    assert asyncio.run(_run("calculator", {"expression": "2 ** 8 + 7 // 2"})) == "259"


def test_calculator_applies_unary_minus():
    assert asyncio.run(_run("calculator", {"expression": "-5"})) == "-5"
    assert asyncio.run(_run("calculator", {"expression": "2 - -3"})) == "5"


def test_calculator_rejects_huge_exponents_instead_of_hanging():
    result = asyncio.run(_run("calculator", {"expression": "9 ** 9 ** 9"}))
    assert "Exponent too large" in result


def test_calculator_errors_never_raise():
    for bad in ["1/0", "__import__('os')", "open('x')", "2 +", "", "abc"]:
        result = asyncio.run(_run("calculator", {"expression": bad}))
        assert result.startswith("Error: "), bad


def test_web_fetch_rejects_file_urls(tmp_path):
    # A fetched page can prompt-inject the model; file:// would let it read local
    # secrets (e.g. backend/.env) and send them out in a second fetch.
    secret = tmp_path / ".env"
    secret.write_text("HF_TOKEN=hf_secret")

    result = asyncio.run(_run("web_fetch", {"url": secret.as_uri()}))

    assert result == "Error: unsupported URL scheme: file"


def test_web_fetch_returns_a_pages_readable_text_not_its_markup():
    # Raw HTML spends the whole character budget on <head>, CSS, scripts and menus.
    html = (
        "<html><head><title>T</title><style>body{color:red}</style>"
        "<script>var tracking = 1;</script></head>"
        "<body><nav>Home | About</nav><h1>Seattle forecast</h1>"
        "<p>Rain,   then\n clearing.</p><p>High 61°F</p></body></html>"
    )

    with _serve_html_once(html) as url:
        result = asyncio.run(_run("web_fetch", {"url": url}))

    assert result == "Seattle forecast\nRain, then clearing.\nHigh 61°F"


def test_web_fetch_keeps_only_the_main_content_when_the_page_marks_it():
    html = (
        "<body><div>Deutsch</div><div>Español</div>"
        "<main><h1>Seattle</h1><p>A seaport city.</p></main><div>Privacy policy</div></body>"
    )

    with _serve_html_once(html) as url:
        assert asyncio.run(_run("web_fetch", {"url": url})) == "Seattle\nA seaport city."


def test_web_fetch_identifies_as_a_browser_not_python_urllib():
    # Many sites 403 urllib's default "Python-urllib/3.x" User-Agent outright.
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers["User-Agent"])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        assert asyncio.run(_run("web_fetch", {"url": url})) == "ok"
    finally:
        server.server_close()

    assert seen[0].startswith("Mozilla/5.0")


def test_web_fetch_rejects_unsupported_scheme():
    result = asyncio.run(_run("web_fetch", {"url": "gopher://example.com/x"}))
    assert result.startswith("Error: ")


def test_registry_list_get_resolve():
    assert {tool.spec.name for tool in list_tools()} == {"calculator", "web_fetch", "web_search"}
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
    assert {tool.spec.name for tool in list_tools()} == {"calculator", "web_fetch", "web_search"}
