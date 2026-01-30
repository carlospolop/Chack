from typing import Optional

from .backends.langchain_backend import build_executor
from .config import ChackConfig


def build_agent(config: ChackConfig, memory=None, system_prompt: Optional[str] = None):
    return build_executor(
        config,
        system_prompt=system_prompt or config.system_prompt,
        memory=memory,
        max_iterations=50,
    ).executor
