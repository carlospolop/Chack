from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from agents import Agent, ModelSettings, Runner
from agents.items import ToolCallItem

from ..config import ChackConfig
from ..long_term_memory import build_long_term_memory, build_memory_summary, format_messages
from ..tools.agents_toolset import AgentsToolset


@dataclass
class ToolAction:
    tool: str
    tool_input: Any


@dataclass
class AgentsExecutor:
    _config: ChackConfig
    agent: Agent
    max_turns: int
    _transcript: list[dict[str, Any]]
    _memory_limit: int
    _memory_reset_to: int
    _summary_text: str
    _summary_max_chars: int
    _memory_summary_prompt: str
    _base_system_prompt: str

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_input = payload.get("input", "")
        if self._summary_text:
            self.agent.instructions = (
                f"{self._base_system_prompt}\n\n### MEMORY SUMMARY\n{self._summary_text}"
            )
        else:
            self.agent.instructions = self._base_system_prompt
        input_items = list(self._transcript)
        if user_input:
            input_items.append({"role": "user", "content": user_input})
        result = Runner.run_sync(
            self.agent,
            input_items,
            max_turns=self.max_turns,
        )
        output = result.final_output or ""
        if user_input:
            self._transcript.append({"role": "user", "content": user_input})
        if output:
            self._transcript.append({"role": "assistant", "content": output})
        if self._memory_limit:
            if len(self._transcript) > self._memory_limit:
                reset_to = self._memory_reset_to or self._memory_limit
                if reset_to > self._memory_limit:
                    reset_to = self._memory_limit
                if reset_to < 1:
                    reset_to = 1
                removed = self._transcript[:-reset_to]
                self._transcript = self._transcript[-reset_to:]
                if removed:
                    conversation = format_messages(removed)
                    self._summary_text = build_memory_summary(
                        self._config,
                        self._memory_summary_prompt,
                        conversation,
                        self._summary_text,
                        self._summary_max_chars,
                    )
        steps = _extract_tool_steps(result.new_items)
        return {
            "output": output,
            "intermediate_steps": steps,
            "raw_result": result,
        }

    async def aget_memory_messages(self) -> list[Any]:
        return list(self._transcript)


def _extract_tool_steps(items: list[Any]) -> list[tuple[ToolAction, Any]]:
    steps: list[tuple[ToolAction, Any]] = []
    for item in items:
        if not isinstance(item, ToolCallItem):
            continue
        raw = item.raw_item
        tool_name = _get_tool_name(raw) or "tool"
        tool_input = _get_tool_input(raw)
        steps.append((ToolAction(tool=tool_name, tool_input=tool_input), None))
    return steps


def _get_tool_name(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if hasattr(raw, "name"):
        return getattr(raw, "name", None)
    if hasattr(raw, "function"):
        func = getattr(raw, "function", None)
        if func and hasattr(func, "name"):
            return getattr(func, "name", None)
    if isinstance(raw, dict):
        name = raw.get("name")
        if name:
            return name
        func = raw.get("function", {})
        if isinstance(func, dict):
            return func.get("name")
    return None


def _get_tool_input(raw: Any) -> Any:
    if raw is None:
        return None
    if hasattr(raw, "arguments"):
        return getattr(raw, "arguments", None)
    if hasattr(raw, "input"):
        return getattr(raw, "input", None)
    if hasattr(raw, "function"):
        func = getattr(raw, "function", None)
        if func and hasattr(func, "arguments"):
            return getattr(func, "arguments", None)
    if isinstance(raw, dict):
        if "arguments" in raw:
            return raw.get("arguments")
        if "input" in raw:
            return raw.get("input")
        func = raw.get("function", {})
        if isinstance(func, dict):
            return func.get("arguments") or func.get("input")
    return None


def build_executor(
    config: ChackConfig,
    *,
    system_prompt: str,
    max_turns: int,
    memory_max_messages: int,
    memory_reset_to_messages: int,
    memory_summary_prompt: str,
    summary_max_chars: int,
) -> AgentsExecutor:
    model_name = config.model.chat or config.model.primary
    temperature = config.model.temperature
    if "chat" in model_name:
        temperature = 1.0

    toolset = AgentsToolset(config.tools)
    agent = Agent(
        name="Chack",
        instructions=system_prompt,
        tools=toolset.tools,
        model=model_name,
        model_settings=ModelSettings(temperature=temperature),
    )

    max_messages = memory_max_messages
    if max_messages < 1:
        max_messages = 1
    reset_to = memory_reset_to_messages
    if reset_to < 1 or reset_to > max_messages:
        reset_to = max_messages
    return AgentsExecutor(
        _config=config,
        agent=agent,
        max_turns=max_turns,
        _transcript=[],
        _memory_limit=max_messages,
        _memory_reset_to=reset_to,
        _summary_text="",
        _summary_max_chars=summary_max_chars,
        _memory_summary_prompt=memory_summary_prompt,
        _base_system_prompt=system_prompt,
    )
