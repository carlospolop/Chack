from __future__ import annotations

from typing import Any

from ..config import ChackConfig
from . import langchain_backend


def build_executor(
    config: ChackConfig,
    *,
    system_prompt: str,
    session_id: str,
    max_turns: int,
    memory_max_messages: int,
    summary_max_chars: int,
):
    backend = (config.agent.backend or "langchain").strip().lower()
    if backend in {"langchain", "lc"}:
        memory = langchain_backend.build_langchain_memory(
            config,
            max_messages=memory_max_messages,
        )
        return langchain_backend.build_executor(
            config,
            system_prompt=system_prompt,
            memory=memory,
            max_iterations=max_turns,
        )
    if backend in {"openai_agents", "openai-agents", "agents", "openai"}:
        from . import openai_agents_backend
        return openai_agents_backend.build_executor(
            config,
            system_prompt=system_prompt,
            session_id=session_id,
            max_turns=max_turns,
            memory_max_messages=memory_max_messages,
            summary_max_chars=summary_max_chars,
        )
    raise ValueError(f"Unknown agent backend: {config.agent.backend}")
