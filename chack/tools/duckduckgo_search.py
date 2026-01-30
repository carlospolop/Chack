from html.parser import HTMLParser
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
from langchain_core.tools import StructuredTool, tool

from ..config import ToolsConfig


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results = []
        self._current_title = ""
        self._current_url = ""
        self._in_result = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "div" and attrs_dict.get("class") == "result__body":
            self._in_result = True
            self._current_title = ""
            self._current_url = ""
        if self._in_result and tag == "a" and attrs_dict.get("class") == "result__a":
            self._in_title = True
            self._current_url = attrs_dict.get("href", "")

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
        if tag == "div" and self._in_result:
            self._in_result = False
            if self._current_title and self._current_url:
                self.results.append(
                    {
                        "title": self._current_title.strip(),
                        "url": _normalize_duckduckgo_url(self._current_url),
                    }
                )
            self._current_title = ""
            self._current_url = ""

    def handle_data(self, data):
        if self._in_title and data:
            self._current_title += data


def _normalize_duckduckgo_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("//"):
        url = f"https:{url}"
    if url.startswith("/"):
        url = f"https://duckduckgo.com{url}"
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if "uddg" in query_params and query_params["uddg"]:
        return unquote(query_params["uddg"][0])
    return url


class DuckDuckGoTool:
    def __init__(self, config: ToolsConfig):
        self.config = config

    def search(self, query: str) -> str:
        return self._duckduckgo_search_impl(query=query)

    def _duckduckgo_search_impl(self, query: str) -> str:
        max_results = self.config.duckduckgo_max_results
        if not query.strip():
            return "ERROR: Query cannot be empty"
        if max_results < 1:
            max_results = 1
        if max_results > 20:
            max_results = 20

        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }

        try:
            response = requests.get(search_url, headers=headers, timeout=20)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            return "ERROR: DuckDuckGo search timed out"
        except requests.exceptions.ConnectionError:
            return "ERROR: Failed to connect to DuckDuckGo"
        except requests.exceptions.HTTPError as exc:
            return f"ERROR: DuckDuckGo returned HTTP {exc.response.status_code}"

        parser = _DuckDuckGoHTMLParser()
        parser.feed(response.text)
        results = parser.results[:max_results]

        if not results:
            return f"SUCCESS: No DuckDuckGo results found for '{query}'"

        lines = [f"SUCCESS: DuckDuckGo results for '{query}' (top {len(results)}):"]
        for idx, result in enumerate(results, start=1):
            lines.append(f"{idx}. {result['title']} - {result['url']}")
        return "\n".join(lines)


def build_duckduckgo_search_tool(config: ToolsConfig) -> StructuredTool:
    helper = DuckDuckGoTool(config)

    def _duckduckgo_search(query: str) -> str:
        """Search DuckDuckGo and return a short list of results."""
        return helper._duckduckgo_search_impl(query=query)

    return StructuredTool.from_function(
        name="duckduckgo_search",
        description=_duckduckgo_search.__doc__ or "Search DuckDuckGo.",
        func=_duckduckgo_search,
    )
