from __future__ import annotations

from langchain.memory import ConversationSummaryBufferMemory
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from .config import ChackConfig


def _message_counter(value) -> int:
    if isinstance(value, list):
        return len(value)
    return len(str(value).splitlines())


class _SafeSummaryBufferMemory(ConversationSummaryBufferMemory):
    trigger_limit: int = 0
    target_limit: int = 0

    def prune(self) -> None:
        buffer = self.chat_memory.messages
        curr_buffer_length = _message_counter(buffer)
        if curr_buffer_length > self.trigger_limit:
            pruned_memory = []
            while curr_buffer_length > self.target_limit and buffer:
                pruned_memory.append(buffer.pop(0))
                curr_buffer_length = _message_counter(buffer)
            if pruned_memory:
                self.moving_summary_buffer = self.predict_new_summary(
                    pruned_memory,
                    self.moving_summary_buffer,
                )

    async def aprune(self) -> None:
        buffer = self.chat_memory.messages
        curr_buffer_length = _message_counter(buffer)
        if curr_buffer_length > self.trigger_limit:
            pruned_memory = []
            while curr_buffer_length > self.target_limit and buffer:
                pruned_memory.append(buffer.pop(0))
                curr_buffer_length = _message_counter(buffer)
            if pruned_memory:
                self.moving_summary_buffer = await self.apredict_new_summary(
                    pruned_memory,
                    self.moving_summary_buffer,
                )


def build_memory(
    config: ChackConfig,
    max_messages: int | None = None,
    reset_to_messages: int | None = None,
    summary_prompt: str | None = None,
) -> ConversationSummaryBufferMemory:
    if max_messages is None:
        max_messages = config.telegram.memory_max_messages
    if max_messages < 1:
        max_messages = 1
    if reset_to_messages is None or reset_to_messages < 1:
        reset_to_messages = max_messages
    if reset_to_messages > max_messages:
        reset_to_messages = max_messages

    prompt = None
    if summary_prompt:
        prompt = PromptTemplate.from_template(summary_prompt)

    model_name = config.model.chat or config.model.primary
    temperature = 0.0
    if "chat" in model_name:
        temperature = 1.0
    summary_llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
    )

    memory_kwargs = {
        "llm": summary_llm,
        "max_token_limit": max_messages,
        "token_counter": _message_counter,
        "return_messages": True,
        "memory_key": "chat_history",
        "output_key": "output",
        "trigger_limit": max_messages,
        "target_limit": reset_to_messages,
    }
    if prompt is not None:
        memory_kwargs["prompt"] = prompt
    memory = _SafeSummaryBufferMemory(**memory_kwargs)
    return memory
