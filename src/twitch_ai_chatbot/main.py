from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from dotenv import load_dotenv

from .config import BotSettings
from .llm import LLMClient
from .memory import RollingMemory
from .persona import Persona
from .stream_observer import StreamObserver
from .twitch_bot import TwitchAIBot
from .twitch_oauth import ensure_valid_twitch_token

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an LLM-powered Twitch AI chatbot.")
    parser.add_argument("--no-chat-context", action="store_true", help="Do not send viewer chat to LLM")
    parser.add_argument("--no-stream", action="store_true", help="Disable video/audio stream observation")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = BotSettings()
    if args.no_chat_context:
        settings.read_chat = False
    if args.no_stream:
        settings.observe_stream = False
    settings.validate_required()

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
    except ValueError as error:
        logger.error("%s", error)


async def run(settings: BotSettings) -> None:
    await ensure_valid_twitch_token(settings)

    persona = Persona.from_settings(settings)
    memory = RollingMemory(
        chat_limit=settings.chat_context_messages,
        observation_limit=settings.observation_context_items,
    )
    llm = LLMClient(settings, persona)
    twitch_bot = TwitchAIBot(settings, llm, memory)
    observer = StreamObserver(settings, llm, memory)

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    observer_task = asyncio.create_task(observer.run(), name="stream-observer")
    bot_task = asyncio.create_task(twitch_bot.start(), name="twitch-chat-bot")

    await stop_event.wait()
    observer.stop()
    bot_task.cancel()
    observer_task.cancel()
    await asyncio.gather(bot_task, observer_task, return_exceptions=True)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            try:
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop_event.set))
            except (OSError, ValueError):
                logger.debug("Could not install handler for signal %s", sig)


if __name__ == "__main__":
    main()
