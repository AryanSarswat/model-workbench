"""Search the web via DuckDuckGo's HTML results page (no API key). Stdlib only,
like web_fetch. The page is scraped, so a DuckDuckGo markup change or rate limit
surfaces as an "Error: ..."/"No results" reply rather than an exception.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from app.tools import ToolSpec
from app.tools.web_fetch import TIMEOUT_SECONDS, USER_AGENT

TOOL_SPEC = ToolSpec(
    name="web_search",
    description=(
        "Search the web and return the top results as title, URL and snippet. "
        "Use web_fetch on a result URL to read the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
)

SEARCH_URL = "https://html.duckduckgo.com/html/"
DEFAULT_RESULTS = 5
MAX_RESULTS = 10


def _real_url(href: str) -> str:
    """Result links go through //duckduckgo.com/l/?uddg=<target>; unwrap them."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return query["uddg"][0] if "uddg" in query else href


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[list[str]] = []  # [title, url, snippet]
        self._field: int | None = None  # index being filled, while inside its <a>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        classes = (dict(attrs).get("class") or "").split()
        if "result__a" in classes:
            self.results.append(["", _real_url(dict(attrs).get("href") or ""), ""])
            self._field = 0
        elif "result__snippet" in classes and self.results:
            self._field = 2

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._field = None

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            self.results[-1][self._field] += data


def parse_results(html: str) -> list[tuple[str, str, str]]:
    """(title, url, snippet) per result, in page order."""
    parser = _ResultParser()
    parser.feed(html)
    return [(title.strip(), url, snippet.strip()) for title, url, snippet in parser.results]


def _search(query: str) -> str:
    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'q': query})}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode(errors="ignore")


async def run(args: dict) -> str:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return "Error: missing 'query' string argument"
    limit = args.get("max_results", DEFAULT_RESULTS)
    limit = min(max(limit, 1), MAX_RESULTS) if isinstance(limit, int) else DEFAULT_RESULTS
    try:
        # to_thread: urlopen blocks, and this runs inside the event loop.
        results = parse_results(await asyncio.to_thread(_search, query))
    except Exception as exc:  # noqa: BLE001 -- contract: failures return "Error: ...", never raise
        return f"Error: {exc}"
    if not results:
        return f"No results for {query!r} (DuckDuckGo may be rate limiting; try again later)."
    return "\n\n".join(
        f"{i}. {title}\n   {url}\n   {snippet}"
        for i, (title, url, snippet) in enumerate(results[:limit], start=1)
    )
