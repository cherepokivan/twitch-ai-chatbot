from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

from twitchio.ext import commands

from .config import BotSettings
from .llm import LLMClient
from .memory import RollingMemory

logger = logging.getLogger(__name__)


class TwitchAIBot(commands.Bot):
    def __init__(self, settings: BotSettings, llm: LLMClient, memory: RollingMemory) -> None:
        super().__init__(
            token=settings.twitch_oauth_token,
            prefix=settings.command_prefix,
            initial_channels=[settings.twitch_channel],
            nick=settings.twitch_bot_nick,
        )
        self.settings = settings
        self.llm = llm
        self.memory = memory
        self._last_reply_at = datetime.min.replace(tzinfo=timezone.utc)
        self._reply_lock = asyncio.Lock()

    async def event_ready(self) -> None:
        logger.info(
            "Logged in as %s; joined #%s",
            self.nick or self.settings.twitch_bot_nick,
            self.settings.twitch_channel,
        )

    async def event_message(self, message) -> None:  # type: ignore[no-untyped-def]
        if message.echo:
            return

        author = message.author.name if message.author else "unknown"
        text = message.content.strip()
        if self.settings.read_chat:
            self.memory.add_chat(author, text)

        await self.handle_commands(message)

        if self._should_reply(author, text):
            await self._reply_to_message(message, author, text)

    @commands.command(name="togglechat")
    async def toggle_chat_context(self, ctx: commands.Context) -> None:
        """Toggle whether viewer chat is stored and sent to the LLM."""
        if not _can_use_admin_commands(ctx, self.settings):
            return
        self.settings.read_chat = not self.settings.read_chat
        state = "включено" if self.settings.read_chat else "выключено"
        await ctx.send(f"Чтение чата для AI-контекста: {state}.")

    @commands.command(name="persona")
    async def persona_info(self, ctx: commands.Context) -> None:
        await ctx.send(
            f"Я {self.settings.bot_persona_name}, {self.settings.bot_persona_age}. "
            f"Роль: {self.settings.bot_persona_role[:250]}"
        )

    def _should_reply(self, author: str, text: str) -> bool:
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_reply_at).total_seconds()
        if elapsed < self.settings.min_seconds_between_replies:
            return False
        if random.random() > self.settings.reply_probability:
            return False

        lower_text = text.lower()
        bot_mentioned = self.settings.twitch_bot_nick in lower_text
        streamer = author.lower() == self.settings.twitch_channel

        if lower_text.startswith(self.settings.command_prefix.lower()):
            return False
        if self.settings.trigger_mode == "all":
            return True
        if self.settings.trigger_mode == "streamer":
            return streamer
        return bot_mentioned or streamer

    async def _reply_to_message(self, message, author: str, text: str) -> None:  # type: ignore[no-untyped-def]
        async with self._reply_lock:
            now = datetime.now(timezone.utc)
            elapsed = (now - self._last_reply_at).total_seconds()
            if elapsed < self.settings.min_seconds_between_replies:
                return
            try:
                chat_context = list(self.memory.chat_context()) if self.settings.read_chat else []
                observation_context = list(self.memory.observation_context())
                reply = await self.llm.build_reply(
                    incoming_author=author,
                    incoming_message=text,
                    chat_context=chat_context,
                    observation_context=observation_context,
                )
                if reply:
                    await message.channel.send(reply)
                    self._last_reply_at = datetime.now(timezone.utc)
            except Exception:  # noqa: BLE001 - chat bot should stay online
                if self.settings.log_tracebacks:
                    logger.exception("Failed to generate/send reply")
                else:
                    logger.warning("Failed to generate/send reply: %s", _format_error())


def _can_use_admin_commands(ctx: commands.Context, settings: BotSettings) -> bool:
    author = ctx.author
    if author is None:
        return False
    author_name = getattr(author, "name", "").lower()
    if author_name in settings.admin_usernames:
        return True
    badges = getattr(author, "badges", {}) or {}
    return bool(badges.get("broadcaster") or badges.get("moderator"))


def _format_error() -> str:
    import sys

    _, error, _ = sys.exc_info()
    return str(error) or error.__class__.__name__ if error else "unknown error"
