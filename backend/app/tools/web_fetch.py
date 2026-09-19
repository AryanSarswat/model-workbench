"""Fetch a URL as text. Stdlib urllib only -- httpx is a dev-only dependency and
must not become a runtime import. Only http(s) (remote pages) and file (local
fixtures/tests) schemes are allowed; everything else is rejected outright.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.parse
import urllib.request

from app.tools import ToolSpec

TOOL_SPEC = ToolSpec(
    name="web_fetch",
    description="Fetch a URL and return its text content (truncated to ~8000 chars).",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)

TIMEOUT_SECONDS = 10
MAX_CHARS = 8000


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_CHARS * 4)
    return raw.decode(errors="ignore")[:MAX_CHARS]


async def run(args: dict) -> str:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return "Error: missing 'url' string argument"
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https", "file"):
        return f"Error: unsupported URL scheme: {scheme or '(none)'}"
    try:
        # to_thread: urlopen blocks, and this runs inside the event loop.
        return await asyncio.to_thread(_fetch, url)
    except Exception as exc:  # noqa: BLE001 -- contract: failures return "Error: ...", never raise
        return f"Error: {exc}"
