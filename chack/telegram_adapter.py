import asyncio
import logging
import os
import re
import time
from typing import List, Optional

from langchain_community.callbacks import get_openai_callback
from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import build_agent
from .config import ChackConfig
from .long_term_memory import (
    build_long_term_memory,
    format_messages,
    get_long_term_memory_path,
    load_long_term_memory,
    save_long_term_memory,
)
from .memory import build_memory
from .pricing import estimate_cost, load_pricing, resolve_pricing_path
from .tools import format_tool_steps


class TelegramBot:
    def __init__(self, config: ChackConfig):
        self.config = config
        self.config_path = os.environ.get("CHACK_CONFIG", "./config/chack.yaml")
        self.logger = logging.getLogger("chack.telegram")
        self._executors = {}
        self._last_bot_reply_at = {}
        self._pricing = load_pricing(resolve_pricing_path())
        self.dm_require = self._compile_patterns(config.telegram.dm_require_regex)
        self.group_require = self._compile_patterns(config.telegram.group_require_regex)
        self.group_title_allow = self._compile_patterns(config.telegram.group_allowlist_title_regex)
        self.dm_user_allow = set(config.telegram.dm_allowlist_ids)
        self.dm_username_allow = set(
            u.lower() for u in config.telegram.dm_allowlist_usernames
        )
        self.dm_username_allow_regex = self._compile_patterns(
            config.telegram.dm_allowlist_usernames_regex
        )

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> List[re.Pattern]:
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                continue
        return compiled

    def _matches_any(self, patterns: List[re.Pattern], text: str) -> bool:
        if not patterns:
            return True
        return any(pattern.search(text) for pattern in patterns)

    def _user_allowed(self, user_id: int, username: Optional[str]) -> bool:
        if not self.dm_user_allow and not self.dm_username_allow and not self.dm_username_allow_regex:
            return True
        if user_id in self.dm_user_allow:
            return True
        if username:
            uname = username.lower()
            if uname in self.dm_username_allow:
                return True
            for pattern in self.dm_username_allow_regex:
                if pattern.search(uname):
                    return True
        return False

    def _group_allowed(self, chat_id: int, title: Optional[str]) -> bool:
        if not self.config.telegram.group_allowlist_ids and not self.group_title_allow:
            return True
        if chat_id in self.config.telegram.group_allowlist_ids:
            return True
        if title:
            return any(pattern.search(title) for pattern in self.group_title_allow)
        return False

    def _message_allowed(self, update: Update) -> bool:
        message = update.effective_message
        if message is None:
            return False
        text = message.text or message.caption or ""
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return False

        if chat.type == ChatType.PRIVATE:
            if not self.config.telegram.allow_dms:
                return False
            if not self._user_allowed(user.id, user.username):
                return False
            return self._matches_any(self.dm_require, text)

        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            if not self.config.telegram.allow_groups:
                return False
            if not self._group_allowed(chat.id, chat.title or ""):
                return False
            return self._matches_any(self.group_require, text)

        return False

    def _chat_allowed(self, update: Update) -> bool:
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return False
        if chat.type == ChatType.PRIVATE:
            if not self.config.telegram.allow_dms:
                return False
            return self._user_allowed(user.id, user.username)
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            if not self.config.telegram.allow_groups:
                return False
            return self._group_allowed(chat.id, chat.title or "")
        return False

    def _get_executor(self, chat_id: int):
        executor = self._executors.get(chat_id)
        if executor is None:
            memory = build_memory(self.config)
            system_prompt = self._system_prompt_for_chat(chat_id)
            executor = build_agent(self.config, memory=memory, system_prompt=system_prompt)
            self._executors[chat_id] = executor
        return executor

    def _system_prompt_for_chat(self, chat_id: int) -> str:
        base = self.config.system_prompt
        if not self.config.telegram.long_term_memory_enabled:
            return base
        path = get_long_term_memory_path(
            self.config_path,
            chat_id,
            self.config.telegram.long_term_memory_dir,
        )
        memory_text = load_long_term_memory(path)
        if not memory_text:
            return base
        return f"{base}\n\n### LONG TERM MEMORY\n{memory_text}"

    async def _finalize_long_term_memory(self, chat_id: int) -> None:
        if not self.config.telegram.long_term_memory_enabled:
            return
        executor = self._executors.get(chat_id)
        if executor is None or not getattr(executor, "memory", None):
            return
        messages = executor.memory.chat_memory.messages
        if not messages:
            return
        path = get_long_term_memory_path(
            self.config_path,
            chat_id,
            self.config.telegram.long_term_memory_dir,
        )
        previous = load_long_term_memory(path)
        conversation = format_messages(messages)
        max_chars = self.config.telegram.long_term_memory_max_chars

        def _build():
            return build_long_term_memory(self.config, conversation, previous, max_chars)

        updated = await asyncio.to_thread(_build)
        if updated:
            save_long_term_memory(path, updated, max_chars)

    async def _run_agent(self, chat_id: int, text: str) -> str:
        reset_minutes = self.config.telegram.memory_reset_minutes
        if reset_minutes and reset_minutes > 0:
            last_reply = self._last_bot_reply_at.get(chat_id)
            if last_reply and (time.time() - last_reply) > reset_minutes * 60:
                await self._finalize_long_term_memory(chat_id)
                self._executors.pop(chat_id, None)
                self._last_bot_reply_at.pop(chat_id, None)
        executor = self._get_executor(chat_id)
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
        max_turns = self.config.telegram.max_turns
        actions = format_tool_steps(steps, max_turns=max_turns, notify_every=10)
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
        # if actions:
        #     return f"{output}\n\nActions performed:\n{actions}{suffix}"
        return f"{output}{suffix}"

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._message_allowed(update):
            return
        message = update.effective_message
        if message is None:
            return
        text = message.text or message.caption or ""
        if not text.strip():
            return
        typing_task = None
        try:
            typing_task = asyncio.create_task(self._keep_typing(message.chat))
            reply = await self._run_agent(message.chat.id, text)
            chunks = self._split_for_telegram(reply, limit=3500)
            for idx, chunk in enumerate(chunks):
                html_chunk = self._markdown_to_html(chunk)
                try:
                    await message.reply_text(html_chunk, parse_mode="HTML")
                except Exception:
                    # Fallback: send without formatting
                    await message.reply_text(chunk)
            self._last_bot_reply_at[message.chat.id] = time.time()
        except Exception as exc:
            self.logger.exception("Failed to process message")
            await message.reply_text("Sorry, I ran into an error while processing that.")
        finally:
            if typing_task:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

    async def _handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_allowed(update):
            return
        chat = update.effective_chat
        if chat is None:
            return
        await self._finalize_long_term_memory(chat.id)
        self._executors.pop(chat.id, None)
        self._last_bot_reply_at.pop(chat.id, None)
        message = update.effective_message
        if message:
            await message.reply_text("Conversation reset.")

    def run(self) -> None:
        if not self.config.telegram.token:
            raise RuntimeError("Telegram token is not configured.")
        application = ApplicationBuilder().token(self.config.telegram.token).build()
        self._app = application
        application.add_handler(CommandHandler("reset", self._handle_reset))
        application.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, self._handle_message))
        self.logger.info("Starting Telegram bot")
        # Disable signal handlers when running from a background thread.
        application.run_polling(stop_signals=None)

    async def _keep_typing(self, chat) -> None:
        # Telegram typing indicator expires quickly; refresh periodically.
        while True:
            try:
                await chat.send_action(ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(4)

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Convert common markdown to Telegram HTML format."""
        import re
        
        # Protect code blocks first (replace with placeholders that won't match markdown)
        code_blocks = []
        def save_code_block(match):
            code_blocks.append(match.group(1))
            return f"§§§CODEBLOCK{len(code_blocks)-1}§§§"
        text = re.sub(r'```(.*?)```', save_code_block, text, flags=re.DOTALL)
        
        # Protect inline code
        inline_codes = []
        def save_inline_code(match):
            inline_codes.append(match.group(1))
            return f"§§§INLINECODE{len(inline_codes)-1}§§§"
        text = re.sub(r'`([^`\n]+?)`', save_inline_code, text)
        
        # Now escape HTML special characters
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Convert markdown headers to bold
        text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
        
        # Convert bold: **text** (non-greedy, doesn't cross newlines)
        text = re.sub(r'\*\*([^\*\n]+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__([^_\n]+?)__', r'<b>\1</b>', text)
        
        # Convert italic: *text* or _text_ (non-greedy, doesn't cross newlines)
        text = re.sub(r'\*([^\*\n]+?)\*', r'<i>\1</i>', text)
        text = re.sub(r'\b_([^_\n]+?)_\b', r'<i>\1</i>', text)
        
        # Restore inline code
        for i, code in enumerate(inline_codes):
            # Escape any HTML that was in the code
            code_escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace(f"§§§INLINECODE{i}§§§", f"<code>{code_escaped}</code>")
        
        # Restore code blocks
        for i, code in enumerate(code_blocks):
            # Escape any HTML that was in the code block
            code_escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace(f"§§§CODEBLOCK{i}§§§", f"<pre>{code_escaped}</pre>")
        
        # Convert links: [text](url) to <a href="url">text</a>
        text = re.sub(r'\[([^\]]+?)\]\(([^\)]+?)\)', r'<a href="\2">\1</a>', text)
        
        return text

    @staticmethod
    def _split_for_telegram(text: str, limit: int = 3500) -> List[str]:
        # Split by lines, keep fenced code blocks balanced within each chunk.
        lines = text.splitlines()
        chunks: List[str] = []
        current: List[str] = []
        in_code = False

        def flush():
            nonlocal current, in_code
            if not current:
                return
            if in_code:
                current.append("```")
            chunks.append("\n".join(current))
            current = []
            if in_code:
                current.append("```")

        for line in lines:
            if line.strip().startswith("```"):
                in_code = not in_code
            candidate = current + [line]
            candidate_len = len("\n".join(candidate))
            if candidate_len > limit and current:
                flush()
                candidate = current + [line]
            # If a single line still too long, split it bluntly.
            if len("\n".join(candidate)) > limit and not current:
                chunk_size = max(500, limit - 200)
                for i in range(0, len(line), chunk_size):
                    chunks.append(line[i : i + chunk_size])
                continue
            current = candidate

        if current:
            if in_code:
                current.append("```")
            chunks.append("\n".join(current))
        return chunks
