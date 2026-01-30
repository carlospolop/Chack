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

from .config import ChackConfig
from .tools import Toolset
from typing import Optional


def build_agent(config: ChackConfig, memory=None, system_prompt: Optional[str] = None) -> AgentExecutor:
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
        max_iterations=50,
    )
    return executor
