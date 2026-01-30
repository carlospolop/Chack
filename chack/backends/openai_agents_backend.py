from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any, Optional

from agents import Agent, ModelSettings, Runner
from agents.items import ToolCallItem
from agents.memory import SQLiteSession

from ..config import ChackConfig
from ..long_term_memory import build_long_term_memory, format_messages
from ..tools.agents_toolset import AgentsToolset


@dataclass
class ToolAction:
    tool: str
    tool_input: Any


def _trim_session(session: SQLiteSession, limit: int) -> None:
    if limit <= 0:
        return
    try:
        items = asyncio.run(session.get_items())
        while len(items) > limit:
            asyncio.run(session.pop_item())
            items = asyncio.run(session.get_items())
    except RuntimeError:
        # If called inside an existing loop, skip trimming to avoid loop errors.
        return


@dataclass
class AgentsExecutor:
    _config: ChackConfig
    agent: Agent
    session: SQLiteSession
    max_turns: int
    _transcript: list[dict[str, Any]]
    _memory_limit: int
    _summary_text: str
    _summary_max_chars: int
    _base_system_prompt: str

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_input = payload.get("input", "")
        if self._summary_text:
            self.agent.instructions = (
                f"{self._base_system_prompt}\n\n### MEMORY SUMMARY\n{self._summary_text}"
            )
        else:
            self.agent.instructions = self._base_system_prompt
        result = Runner.run_sync(
            self.agent,
            user_input,
            session=self.session,
            max_turns=self.max_turns,
        )
        output = result.final_output or ""
        if user_input:
            self._transcript.append({"role": "user", "content": user_input})
        if output:
            self._transcript.append({"role": "assistant", "content": output})
        if self._memory_limit:
            _trim_session(self.session, self._memory_limit)
            if len(self._transcript) > self._memory_limit:
                removed = self._transcript[:-self._memory_limit]
                self._transcript = self._transcript[-self._memory_limit :]
                if removed:
                    conversation = format_messages(removed)
                    self._summary_text = build_long_term_memory(
                        self._config,
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
    session_id: str,
    max_turns: int,
    memory_max_messages: int,
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
    session = SQLiteSession(session_id=session_id)
    return AgentsExecutor(
        _config=config,
        agent=agent,
        session=session,
        max_turns=max_turns,
        _transcript=[],
        _memory_limit=max_messages,
        _summary_text="",
        _summary_max_chars=summary_max_chars,
        _base_system_prompt=system_prompt,
    )
