from __future__ import annotations

from langchain.memory import ConversationSummaryBufferMemory
from langchain_openai import ChatOpenAI

from .config import ChackConfig


def _message_counter(value) -> int:
    if isinstance(value, list):
        return len(value)
    return len(str(value).splitlines())


class _SafeSummaryBufferMemory(ConversationSummaryBufferMemory):
    def prune(self) -> None:
        buffer = self.chat_memory.messages
        curr_buffer_length = _message_counter(buffer)
        if curr_buffer_length > self.max_token_limit:
            pruned_memory = []
            while curr_buffer_length > self.max_token_limit and buffer:
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
        if curr_buffer_length > self.max_token_limit:
            pruned_memory = []
            while curr_buffer_length > self.max_token_limit and buffer:
                pruned_memory.append(buffer.pop(0))
                curr_buffer_length = _message_counter(buffer)
            if pruned_memory:
                self.moving_summary_buffer = await self.apredict_new_summary(
                    pruned_memory,
                    self.moving_summary_buffer,
                )


def build_memory(config: ChackConfig, max_messages: int | None = None) -> ConversationSummaryBufferMemory:
    if max_messages is None:
        max_messages = config.telegram.memory_max_messages
    if max_messages < 1:
        max_messages = 1

    model_name = config.model.chat or config.model.primary
    temperature = 0.0
    if "chat" in model_name:
        temperature = 1.0
    summary_llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
    )

    memory = _SafeSummaryBufferMemory(
        llm=summary_llm,
        max_token_limit=max_messages,
        token_counter=_message_counter,
        return_messages=True,
        memory_key="chat_history",
        output_key="output",
    )
    return memory
