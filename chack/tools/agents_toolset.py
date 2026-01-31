import os
import subprocess
from typing import Optional

from agents import function_tool

from ..config import ToolsConfig
from .brave_search import BraveSearchTool
from .duckduckgo_search import DuckDuckGoTool
from .formatting import _truncate


def _exec_command(command: str) -> str:
    timeout = int(os.environ.get("CHACK_EXEC_TIMEOUT", "120"))
    max_chars = int(os.environ.get("CHACK_EXEC_MAX_OUTPUT", "4000"))
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip() or "(no output)"
    return _truncate(output, max_chars)


class AgentsToolset:
    def __init__(self, config: ToolsConfig):
        self.config = config
        self.tools = self._build_tools()

    @staticmethod
    def _make_duckduckgo_tool(helper: DuckDuckGoTool):
        @function_tool(name_override="duckduckgo_search")
        def duckduckgo_search(query: str) -> str:
            """Search DuckDuckGo and return a short list of results."""
            return helper._duckduckgo_search_impl(query=query)

        return duckduckgo_search

    @staticmethod
    def _make_brave_tool(helper: BraveSearchTool):
        @function_tool(name_override="brave_search")
        def brave_search(
            query: str,
            count: Optional[int] = None,
            country: Optional[str] = None,
            search_lang: Optional[str] = None,
            ui_lang: Optional[str] = None,
            freshness: Optional[str] = None,
            timeout_seconds: int = 20,
        ) -> str:
            """Search Brave Search API and return a short list of results."""
            try:
                return helper._brave_search_impl(
                    query=query,
                    count=count,
                    country=country,
                    search_lang=search_lang,
                    ui_lang=ui_lang,
                    freshness=freshness,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                return f"ERROR: Brave search failed ({exc})"

        return brave_search

    def _build_tools(self):
        tools = []
        if self.config.exec_enabled:
            @function_tool(name_override="exec")
            def exec_tool(command: str) -> str:
                """Execute a shell command locally and return combined output."""
                return _exec_command(command)

            tools.append(exec_tool)

        if self.config.duckduckgo_enabled:
            ddg_helper = DuckDuckGoTool(self.config)
            tools.append(self._make_duckduckgo_tool(ddg_helper))

        if self.config.brave_enabled:
            brave_helper = BraveSearchTool(self.config)
            tools.append(self._make_brave_tool(brave_helper))

        return tools
