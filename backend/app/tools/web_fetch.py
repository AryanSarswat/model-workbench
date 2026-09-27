"""Fetch a URL as text. Stdlib urllib only -- httpx is a dev-only dependency and
must not become a runtime import. Only http(s) is allowed; everything else is
rejected outright -- file:// would let a prompt-injected page have the model read
local secrets (e.g. backend/.env).
"""

from __future__ import annotations

import asyncio
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from app.tools import ToolSpec

TOOL_SPEC = ToolSpec(
    name="web_fetch",
    description=(
        "Fetch a URL and return its text content (HTML pages as readable text, "
        "truncated to ~8000 chars)."
    ),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)

TIMEOUT_SECONDS = 10
MAX_CHARS = 8000
# Raw bytes read before extracting text: a page's text is a small slice of its markup,
# so reading only MAX_CHARS worth could stop inside <head>.
MAX_BYTES = 1_000_000
# Many sites reject urllib's default "Python-urllib/3.x" outright.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)


# Content that isn't the page's text (never shown, or site chrome that would eat the
# character budget), and elements that start a new line of text.
_SKIPPED = {"aside", "footer", "head", "nav", "noscript", "script", "style", "svg", "template"}
_BLOCKS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "figcaption", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "td", "th",
    "tr", "ul",
}  # fmt: skip


# When a page marks its main content, that's all the reader wants (most-specific first).
_CONTENT_ROOTS = ("main", "article")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()  # convert_charrefs=True: &amp; etc. arrive decoded
        self.parts: dict[str | None, list[str]] = {None: [], "main": [], "article": []}
        self._skip_depth = 0
        self._root_depth = {"main": 0, "article": 0}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED:
            self._skip_depth += 1
        elif tag in self._root_depth:
            self._root_depth[tag] += 1
        if tag in _BLOCKS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED:
            self._skip_depth = max(self._skip_depth - 1, 0)
        elif tag in self._root_depth:
            self._root_depth[tag] = max(self._root_depth[tag] - 1, 0)
        if tag in _BLOCKS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        # Source newlines inside text are just whitespace in HTML; only block
        # elements start a new line.
        self._emit(re.sub(r"\s+", " ", data))

    def _emit(self, text: str) -> None:
        if self._skip_depth:
            return
        self.parts[None].append(text)
        for root, depth in self._root_depth.items():
            if depth:
                self.parts[root].append(text)


def html_to_text(html: str) -> str:
    """Visible text of the page's <main> (else <article>, else everything), one line
    per block element, whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(html)
    text = next(
        (
            joined
            for root in (*_CONTENT_ROOTS, None)
            if (joined := "".join(extractor.parts[root])).strip()
        ),
        "",
    )
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_BYTES)
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="ignore")
    if content_type == "text/html":
        text = html_to_text(text)
    return text[:MAX_CHARS]


async def run(args: dict) -> str:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return "Error: missing 'url' string argument"
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return f"Error: unsupported URL scheme: {scheme or '(none)'}"
    try:
        # to_thread: urlopen blocks, and this runs inside the event loop.
        return await asyncio.to_thread(_fetch, url)
    except Exception as exc:  # noqa: BLE001 -- contract: failures return "Error: ...", never raise
        return f"Error: {exc}"
