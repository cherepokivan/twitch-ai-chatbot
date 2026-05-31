from __future__ import annotations

import base64
from pathlib import Path

from openai import AsyncOpenAI

from .config import BotSettings
from .persona import Persona


class LLMClient:
    def __init__(self, settings: BotSettings, persona: Persona) -> None:
        self.settings = settings
        self.persona = persona
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

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
        response = await self.client.responses.create(
            model=self.settings.openai_chat_model,
            instructions=self.persona.system_prompt(
                self.settings.twitch_channel, self.settings.max_reply_chars
            ),
            input=prompt,
            temperature=0.8,
            max_output_tokens=180,
        )
        return _sanitize_reply(response.output_text, self.settings.max_reply_chars)

    async def summarize_frame(self, frame_path: Path) -> str:
        encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        response = await self.client.responses.create(
            model=self.settings.openai_vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Коротко опиши, что сейчас видно на Twitch-стриме. "
                                "Сфокусируйся на игре/сцене, важных событиях, тексте на экране. "
                                "Ответь одним предложением на русском."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{encoded}",
                        },
                    ],
                }
            ],
            max_output_tokens=120,
        )
        return response.output_text.strip()

    async def transcribe_audio(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            transcription = await self.client.audio.transcriptions.create(
                model=self.settings.openai_transcription_model,
                file=audio_file,
            )
        return getattr(transcription, "text", "").strip()

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
