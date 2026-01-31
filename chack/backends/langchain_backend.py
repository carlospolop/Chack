from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

try:
    from langchain.agents import AgentExecutor, create_openai_tools_agent
except ImportError:  # pragma: no cover - fallback for newer langchain layouts
    try:
        from langchain.agents.openai_tools import create_openai_tools_agent
    except ImportError:
        from langchain.agents import create_openai_tools_agent
    from langchain.agents.agent import AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from ..config import ChackConfig
from ..tools.toolset import Toolset
from ..memory import build_memory


@dataclass
class LangchainExecutor:
    executor: AgentExecutor

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.executor.invoke(payload)

    async def aget_memory_messages(self) -> list[Any]:
        if not getattr(self.executor, "memory", None):
            return []
        return list(self.executor.memory.chat_memory.messages)


def build_executor(
    config: ChackConfig,
    *,
    system_prompt: str,
    memory=None,
    max_iterations: int = 50,
) -> LangchainExecutor:
    model_name = config.model.chat or config.model.primary
    temperature = config.model.temperature
    if "chat" in model_name:
        temperature = 1.0
    llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
    )

    toolset = Toolset(config.tools)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt or config.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_openai_tools_agent(llm, toolset.tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=toolset.tools,
        verbose=False,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
        memory=memory,
        max_iterations=max_iterations,
    )
    return LangchainExecutor(executor=executor)


def build_langchain_memory(
    config: ChackConfig,
    max_messages: int | None = None,
    reset_to_messages: int | None = None,
    summary_prompt: str | None = None,
):
    return build_memory(
        config,
        max_messages=max_messages,
        reset_to_messages=reset_to_messages,
        summary_prompt=summary_prompt,
    )
