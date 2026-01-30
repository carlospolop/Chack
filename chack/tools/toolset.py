from ..config import ToolsConfig
from .brave_search import build_brave_search_tool
from .duckduckgo_search import build_duckduckgo_search_tool
from .exec_tool import exec_tool


class Toolset:
    def __init__(self, config: ToolsConfig):
        self.config = config
        self.tools = self._build_tools()

    def _build_tools(self):
        tools = []
        if self.config.exec_enabled:
            tools.append(exec_tool)
        if self.config.duckduckgo_enabled:
            tools.append(build_duckduckgo_search_tool(self.config))
        if self.config.brave_enabled:
            tools.append(build_brave_search_tool(self.config))
        return tools
