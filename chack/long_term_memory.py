from __future__ import annotations

import os
from typing import Iterable, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .config import ChackConfig


def _resolve_dir(config_path: str, rel_dir: str) -> str:
    if os.path.isabs(rel_dir):
        return rel_dir
    base_dir = os.path.dirname(os.path.abspath(config_path))
    return os.path.normpath(os.path.join(base_dir, rel_dir))


def get_long_term_memory_path(config_path: str, chat_id: int, rel_dir: str) -> str:
    directory = _resolve_dir(config_path, rel_dir)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{chat_id}.txt")


def load_long_term_memory(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def save_long_term_memory(path: str, content: str, max_chars: int) -> None:
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars].rstrip()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def format_messages(messages: Iterable) -> str:
    lines = []
    for msg in messages:
        role = getattr(msg, "type", msg.__class__.__name__).lower()
        content = getattr(msg, "content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def build_long_term_memory(
    config: ChackConfig,
    conversation_text: str,
    previous_memory: str,
    max_chars: int,
) -> str:
    model_name = config.model.chat or config.model.primary
    temperature = 0.0
    if "chat" in model_name:
        temperature = 1.0

    llm = ChatOpenAI(model=model_name, temperature=temperature)

    system = config.telegram.long_term_memory_summary_prompt.replace("{max_chars}", str(max_chars))

    human = (
        "### Previous memory (if any):\n"
        f"{previous_memory or 'None'}\n\n"
        "### Full conversation:\n"
        f"{conversation_text}\n\n"
        "### Write the updated long-term memory now."
    )

    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    content = getattr(response, "content", "") or ""
    content = content.strip()
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars].rstrip()
    return content
