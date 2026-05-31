from __future__ import annotations

import asyncio
import base64
import json
import wave
from pathlib import Path

from groq import AsyncGroq
from openai import AsyncOpenAI
from vosk import KaldiRecognizer, Model

from .config import BotSettings
from .persona import Persona


class LLMClient:
    def __init__(self, settings: BotSettings, persona: Persona) -> None:
        self.settings = settings
        self.persona = persona
        self.client = AsyncOpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        self.groq_client = (
            AsyncGroq(api_key=settings.groq_api_key)
            if settings.llm_provider == "groq"
            else None
        )
        self.vosk_model = Model(str(settings.vosk_model_path)) if settings.vosk_enabled else None

    async def build_reply(
        self,
        *,
        incoming_author: str,
        incoming_message: str,
        chat_context: list[str],
        observation_context: list[str],
    ) -> str:
        prompt = self._reply_prompt(
            incoming_author=incoming_author,
            incoming_message=incoming_message,
            chat_context=chat_context,
            observation_context=observation_context,
        )
        response = await self.client.chat.completions.create(
            model=self.settings.active_chat_model,
            messages=[
                {
                    "role": "system",
                    "content": self.persona.system_prompt(
                        self.settings.twitch_channel, self.settings.max_reply_chars
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=180,
        )
        reply = response.choices[0].message.content or ""
        return _sanitize_reply(reply, self.settings.max_reply_chars)

    async def summarize_frame(self, frame_path: Path) -> str:
        if not self.settings.active_vision_model:
            raise RuntimeError(
                "Video observation requires a vision-capable model. "
                "Set GROQ_VISION_MODEL or disable OBSERVE_VIDEO."
            )

        encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        response = await self.client.chat.completions.create(
            model=self.settings.active_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Коротко опиши, что сейчас видно на Twitch-стриме. "
                                "Сфокусируйся на игре/сцене, важных событиях, тексте на экране. "
                                "Ответь одним предложением на русском."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                        },
                    ],
                }
            ],
            max_tokens=120,
        )
        return (response.choices[0].message.content or "").strip()

    async def transcribe_audio(self, audio_path: Path) -> str:
        if self.settings.vosk_enabled:
            return await asyncio.to_thread(self._transcribe_audio_with_vosk, audio_path)

        if self.settings.llm_provider == "groq":
            if self.groq_client is None:
                raise RuntimeError("Groq client is not configured")
            with audio_path.open("rb") as audio_file:
                transcription = await self.groq_client.audio.transcriptions.create(
                    file=(audio_path.name, audio_file.read()),
                    model=self.settings.active_transcription_model,
                    temperature=0,
                    response_format="verbose_json",
                )
            return getattr(transcription, "text", "").strip()

        with audio_path.open("rb") as audio_file:
            transcription = await self.client.audio.transcriptions.create(
                model=self.settings.active_transcription_model,
                file=audio_file,
            )
        return getattr(transcription, "text", "").strip()

    def _transcribe_audio_with_vosk(self, audio_path: Path) -> str:
        if self.vosk_model is None:
            raise RuntimeError("Vosk model is not configured")

        chunks: list[str] = []
        with wave.open(str(audio_path), "rb") as audio_file:
            recognizer = KaldiRecognizer(self.vosk_model, audio_file.getframerate())
            recognizer.SetWords(False)
            while True:
                data = audio_file.readframes(4000)
                if not data:
                    break
                if recognizer.AcceptWaveform(data):
                    text = json.loads(recognizer.Result()).get("text", "")
                    if text:
                        chunks.append(text)
            final_text = json.loads(recognizer.FinalResult()).get("text", "")
            if final_text:
                chunks.append(final_text)
        return " ".join(chunks).strip()

    def _reply_prompt(
        self,
        *,
        incoming_author: str,
        incoming_message: str,
        chat_context: list[str],
        observation_context: list[str],
    ) -> str:
        chat_block = "\n".join(chat_context) if chat_context else "Чтение чата выключено или контекста нет."
        obs_block = "\n".join(observation_context) if observation_context else "Наблюдений стрима пока нет."
        return f"""
Контекст стрима:
{obs_block}

Последние сообщения чата:
{chat_block}

Новое сообщение, на которое можно ответить:
{incoming_author}: {incoming_message}

Сформулируй одно сообщение в Twitch-чат от лица персонажа.
""".strip()


def _sanitize_reply(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.replace("\n", " ").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"
