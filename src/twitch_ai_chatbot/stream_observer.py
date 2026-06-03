from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from streamlink import Streamlink

from .config import BotSettings
from .llm import LLMClient
from .memory import RollingMemory

logger = logging.getLogger(__name__)

ObservationCallback = Callable[[str, str], Awaitable[None]]


class StreamOfflineError(RuntimeError):
    pass


class StreamObserver:
    """Captures Twitch video/audio samples and turns them into short LLM-readable notes."""

    def __init__(self, settings: BotSettings, llm: LLMClient, memory: RollingMemory) -> None:
        self.settings = settings
        self.llm = llm
        self.memory = memory
        self._stop = asyncio.Event()

    async def run(self) -> None:
        if not self.settings.observe_stream:
            logger.info("Stream observation is disabled")
            return

        await self._ensure_ffmpeg()
        video_task = None
        audio_task = None
        if self.settings.observe_video:
            video_task = asyncio.create_task(self._video_loop(), name="stream-video-observer")
        if self.settings.observe_audio:
            audio_task = asyncio.create_task(self._audio_loop(), name="stream-audio-observer")

        tasks = [task for task in (video_task, audio_task) if task is not None]
        if not tasks:
            return
        await asyncio.gather(*tasks)

    def stop(self) -> None:
        self._stop.set()

    async def _video_loop(self) -> None:
        while not self._stop.is_set():
            try:
                stream_url = await asyncio.to_thread(self._resolve_stream_url)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    frame_path = Path(tmp.name)
                try:
                    await self._run_ffmpeg(
                        "-y",
                        "-i",
                        stream_url,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "3",
                        str(frame_path),
                    )
                    summary = await self.llm.summarize_frame(frame_path)
                    self.memory.add_observation("видео", summary)
                    logger.info("Video observation: %s", summary)
                finally:
                    frame_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001 - keep long-running observer alive
                self._log_observer_error("video")
            await asyncio.sleep(self.settings.frame_interval_seconds)

    async def _audio_loop(self) -> None:
        while not self._stop.is_set():
            try:
                stream_url = await asyncio.to_thread(self._resolve_stream_url)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    audio_path = Path(tmp.name)
                try:
                    await self._run_ffmpeg(
                        "-y",
                        "-i",
                        stream_url,
                        "-t",
                        str(self.settings.audio_interval_seconds),
                        "-vn",
                        "-acodec",
                        "pcm_s16le",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(audio_path),
                    )
                    text = await self.llm.transcribe_audio(audio_path)
                    if text:
                        self.memory.add_observation("аудио", text)
                        logger.info("Audio observation: %s", text)
                finally:
                    audio_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001 - keep long-running observer alive
                self._log_observer_error("audio")
            await asyncio.sleep(self.settings.audio_interval_seconds)

    def _resolve_stream_url(self) -> str:
        session = Streamlink()
        session.set_option("http-trust-env", self.settings.streamlink_trust_env)
        streams = session.streams(f"https://www.twitch.tv/{self.settings.twitch_channel}")
        if not streams:
            raise StreamOfflineError(f"No live stream found for {self.settings.twitch_channel}")
        stream = streams.get("best") or next(iter(streams.values()))
        return stream.to_url()

    def _log_observer_error(self, kind: str) -> None:
        _, error, _ = sys.exc_info()
        if isinstance(error, StreamOfflineError):
            logger.warning("%s observation skipped: %s", kind.capitalize(), error)
            return
        if self.settings.log_tracebacks:
            logger.exception("Failed to observe stream %s", kind)
            return
        logger.warning("Failed to observe stream %s: %s", kind, error)

    async def _run_ffmpeg(self, *args: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace"))

    async def _ensure_ffmpeg(self) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        if process.returncode != 0:
            raise RuntimeError("ffmpeg is required for stream observation")
