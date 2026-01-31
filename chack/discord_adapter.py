import asyncio
import logging
import os
import time
from typing import Optional

import discord
from discord.ext import commands
from langchain_community.callbacks import get_openai_callback

from .backends import build_executor
from .config import ChackConfig
from .long_term_memory import (
    build_long_term_memory,
    format_messages,
    get_long_term_memory_path,
    load_long_term_memory,
    save_long_term_memory,
)
from .pricing import estimate_cost, load_pricing, resolve_pricing_path
from .tools import format_tool_steps


class DiscordBot(commands.Bot):
    def __init__(self, config: ChackConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.config = config
        self.config_path = os.environ.get("CHACK_CONFIG", "./config/chack.yaml")
        self.logger = logging.getLogger("chack.discord")
        self._executors = {}
        self._last_bot_reply_at = {}
        self._pricing = load_pricing(resolve_pricing_path())

    async def on_ready(self):
        guild_names = [g.name for g in self.guilds]
        self.logger.info(f"Discord bot logged in as {self.user} (guilds: {guild_names})")

    async def _get_or_create_thread(self, message: discord.Message):
        """Get existing thread for message or create a new one."""
        # If already inside a thread, reuse it.
        if isinstance(message.channel, discord.Thread):
            return message.channel
        # Check if message already has a thread
        if hasattr(message, 'thread') and message.thread:
            return message.thread
        
        # Create a new thread from this message
        thread_name = f"CodeBuild Analysis - {message.created_at.strftime('%H:%M:%S')}"
        thread = await message.create_thread(
            name=thread_name,
            auto_archive_duration=60  # Auto-archive after 1 hour of inactivity
        )
        return thread

    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.user:
            return

        channel_id = message.channel.id
        if isinstance(message.channel, discord.Thread) and message.channel.parent_id:
            channel_id = message.channel.parent_id

        # Check if message is from allowed channel
        if channel_id not in self.config.discord.channel_ids:
            self.logger.info(
                "Discord message ignored (channel not allowed). "
                "channel_id=%s parent_id=%s thread=%s author=%s",
                message.channel.id,
                getattr(message.channel, "parent_id", None),
                isinstance(message.channel, discord.Thread),
                message.author,
            )
            return

        # Check if message contains trigger word
        content_lower = message.content.lower()
        if not any(trigger.lower() in content_lower for trigger in self.config.discord.trigger_words):
            self.logger.info(
                "Discord message ignored (no trigger). channel_id=%s content_len=%s",
                channel_id,
                len(message.content or ""),
            )
            return

        # Process the message
        try:
            async with message.channel.typing():
                reply = await self._run_agent(message.channel.id, message.content)
                
                # Get or create thread for this message
                thread = await self._get_or_create_thread(message)
                status_msg = None
                try:
                    status_msg = await thread.send("Working on it…")
                except Exception:
                    status_msg = None
                
                # Discord has a 2000 character limit per message
                chunks = self._split_for_discord(reply, limit=1900)
                for chunk in chunks:
                    await thread.send(chunk)
                
                if status_msg:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                self._last_bot_reply_at[message.channel.id] = time.time()
        except Exception as exc:
            self.logger.exception("Failed to process Discord message")
            try:
                thread = await self._get_or_create_thread(message)
                await thread.send("Sorry, I ran into an error while processing that.")
            except:
                await message.reply("Sorry, I ran into an error while processing that.")

    def _get_executor(self, channel_id: int):
        executor = self._executors.get(channel_id)
        if executor is None:
            system_prompt = self._system_prompt_for_channel(channel_id)
            executor = build_executor(
                self.config,
                system_prompt=system_prompt,
                max_turns=self.config.discord.max_turns,
                memory_max_messages=self.config.discord.memory_max_messages,
                memory_reset_to_messages=self.config.discord.memory_reset_to_messages,
                memory_summary_prompt=(
                    self.config.discord.memory_summary_prompt
                    or self.config.telegram.memory_summary_prompt
                ),
                summary_max_chars=self.config.discord.long_term_memory_max_chars,
            )
            self._executors[channel_id] = executor
        return executor

    def _system_prompt_for_channel(self, channel_id: int) -> str:
        # Use Discord-specific system prompt if configured, otherwise use main system prompt
        base = self.config.discord.system_prompt if self.config.discord.system_prompt else self.config.system_prompt
        if not self.config.discord.long_term_memory_enabled:
            return base
        path = get_long_term_memory_path(
            self.config_path,
            channel_id,
            self.config.discord.long_term_memory_dir,
        )
        memory_text = load_long_term_memory(path)
        if not memory_text:
            return base
        return f"{base}\n\n### LONG TERM MEMORY\n{memory_text}"

    async def _finalize_long_term_memory(self, channel_id: int) -> None:
        if not self.config.discord.long_term_memory_enabled:
            return
        executor = self._executors.get(channel_id)
        if executor is None:
            return
        messages = await executor.aget_memory_messages()
        if not messages:
            return
        path = get_long_term_memory_path(
            self.config_path,
            channel_id,
            self.config.discord.long_term_memory_dir,
        )
        previous = load_long_term_memory(path)
        conversation = format_messages(messages)
        max_chars = self.config.discord.long_term_memory_max_chars

        def _build():
            summary_prompt = self.config.discord.long_term_memory_summary_prompt
            if not summary_prompt:
                summary_prompt = self.config.telegram.long_term_memory_summary_prompt
            return build_long_term_memory(self.config, conversation, previous, max_chars)

        updated = await asyncio.to_thread(_build)
        if updated:
            save_long_term_memory(path, updated, max_chars)

    async def _run_agent(self, channel_id: int, text: str) -> str:
        reset_minutes = self.config.discord.memory_reset_minutes
        if reset_minutes and reset_minutes > 0:
            last_reply = self._last_bot_reply_at.get(channel_id)
            if last_reply and (time.time() - last_reply) > reset_minutes * 60:
                await self._finalize_long_term_memory(channel_id)
                self._executors.pop(channel_id, None)
                self._last_bot_reply_at.pop(channel_id, None)
        
        executor = self._get_executor(channel_id)
        min_tools_used = max(0, int(self.config.tools.min_tools_used or 0))
        max_attempts = 20
        result = {}
        cb = None
        for attempt in range(max_attempts):
            attempt_text = text
            if attempt and min_tools_used > 0:
                attempt_text = (
                    f"{text}\n\nIMPORTANT: Use at least {min_tools_used} tools before your final answer. "
                    "Always use tools to check for more data, confirm actions were performed, or verify "
                    "assumptions by searching the internet."
                )
            with get_openai_callback() as attempt_cb:
                result = await asyncio.to_thread(executor.invoke, {"input": attempt_text})
            cb = attempt_cb
            steps = result.get("intermediate_steps", [])
            if min_tools_used <= 0 or len(steps) >= min_tools_used:
                break
        else:
            raise RuntimeError(
                f"Minimum tool usage requirement not met: {min_tools_used} tools."
            )
        
        prompt_tokens = int(getattr(cb, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(cb, "completion_tokens", 0) or 0)
        cached_prompt_tokens = int(
            getattr(cb, "prompt_tokens_cached", getattr(cb, "cached_prompt_tokens", 0)) or 0
        )
        output = result.get("output", "")
        steps = result.get("intermediate_steps", [])
        max_turns = self.config.discord.max_turns
        rounds_used = len(steps) + 1 if output else len(steps)
        tools_used = len(steps)
        model_name = self.config.model.chat or self.config.model.primary
        cost = estimate_cost(
            self._pricing,
            model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
        )
        cost_text = f"${cost:.6f}" if cost is not None else "unknown"
        suffix = f"\n\n🔁 {rounds_used}/{max_turns} | 🧰 {tools_used} | 💲 {cost_text}"
        return f"{output}{suffix}"

    @staticmethod
    def _split_for_discord(text: str, limit: int = 1900):
        """Split text into chunks that fit Discord's message limit."""
        if len(text) <= limit:
            return [text]
        
        chunks = []
        lines = text.splitlines()
        current = []
        
        for line in lines:
            candidate = current + [line]
            if len("\n".join(candidate)) > limit and current:
                chunks.append("\n".join(current))
                current = [line]
            else:
                current = candidate
        
        if current:
            chunks.append("\n".join(current))
        
        return chunks


def run_discord_bot(config: ChackConfig):
    """Run the Discord bot."""
    if not config.discord.token:
        raise RuntimeError("Discord token is not configured.")
    
    bot = DiscordBot(config)
    bot.run(config.discord.token)
