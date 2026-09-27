"""web_search: DuckDuckGo's HTML results page parsed into a short, numbered list."""

import asyncio

import pytest

from app.tools import get_tool
from app.tools.web_search import parse_results

# Trimmed from a real html.duckduckgo.com response: result links go through a
# //duckduckgo.com/l/?uddg=<target> redirect and snippets carry <b> highlights.
_PAGE = """
<div class="result results_links web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.com%2Fseattle&amp;rut=abc">10-Day Forecast for Seattle &amp; Area</a>
  </h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.com%2Fseattle">Accurate 10-day <b>forecast</b> for <b>Seattle</b>.</a>
</div>
<div class="result results_links web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://www.weather.gov/sew/">NWS Seattle</a>
  </h2>
  <a class="result__snippet" href="https://www.weather.gov/sew/">Official forecasts.</a>
</div>
"""


def _run(args: dict) -> str:
    return asyncio.run(get_tool("web_search").run(args))


def test_parses_titles_real_urls_and_plain_snippets():
    assert parse_results(_PAGE) == [
        (
            "10-Day Forecast for Seattle & Area",
            "https://weather.com/seattle",
            "Accurate 10-day forecast for Seattle.",
        ),
        ("NWS Seattle", "https://www.weather.gov/sew/", "Official forecasts."),
    ]


def test_missing_query_is_an_error_result_not_an_exception():
    assert _run({}).startswith("Error: ")
    assert _run({"query": "   "}).startswith("Error: ")


@pytest.mark.network
def test_live_search_returns_numbered_results_with_urls():
    result = _run({"query": "python programming language", "max_results": 3})

    assert result.startswith("1. ")
    assert "http" in result
