from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """Runtime settings loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    twitch_oauth_token: str = Field(
        default="", description="OAuth token for the bot account, usually oauth:..."
    )
    twitch_bot_nick: str = Field(default="", description="Twitch login of the bot account")
    twitch_channel: str = Field(default="", description="Streamer/channel to join without #")

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_chat_model: str = Field(default="gpt-4.1-mini", description="LLM used for replies")
    openai_vision_model: str = Field(
        default="gpt-4.1-mini", description="Vision-capable model used to summarize frames"
    )
    openai_transcription_model: str = Field(
        default="gpt-4o-mini-transcribe", description="Audio transcription model"
    )

    bot_persona_name: str = Field(default="Света")
    bot_persona_age: int = Field(default=22)
    bot_persona_role: str = Field(
        default=(
            "дружелюбная, немного ироничная AI-подруга стримера; отвечает коротко, "
            "живым разговорным русским языком, без токсичности и спама"
        )
    )
    bot_persona_extra: str = Field(default="")

    read_chat: bool = Field(default=True, description="Whether the bot may use viewer chat as context")
    observe_stream: bool = Field(default=True, description="Whether to analyze video/audio from stream")
    observe_video: bool = Field(default=True, description="Whether to capture stream frames")
    observe_audio: bool = Field(default=True, description="Whether to capture stream audio")

    frame_interval_seconds: int = Field(default=30, ge=5)
    audio_interval_seconds: int = Field(default=30, ge=5)
    chat_context_messages: int = Field(default=30, ge=0, le=200)
    observation_context_items: int = Field(default=12, ge=0, le=50)
    min_seconds_between_replies: int = Field(default=20, ge=0)
    max_reply_chars: int = Field(default=420, ge=50, le=500)
    reply_probability: float = Field(default=1.0, ge=0.0, le=1.0)

    trigger_mode: Literal["mention", "all", "streamer"] = Field(
        default="mention",
        description=(
            "mention: answer only when mentioned or streamer writes; all: may answer every message; "
            "streamer: answer only to streamer messages"
        ),
    )
    command_prefix: str = Field(default="!ai")
    data_dir: Path = Field(default=Path(".bot-data"))

    @field_validator("twitch_channel", "twitch_bot_nick")
    @classmethod
    def normalize_twitch_names(cls, value: str) -> str:
        return value.strip().lower().lstrip("#")

    @field_validator("twitch_oauth_token")
    @classmethod
    def normalize_oauth(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith("oauth:"):
            return f"oauth:{value}"
        return value

    def validate_required(self) -> None:
        missing = []
        for field_name in (
            "twitch_oauth_token",
            "twitch_bot_nick",
            "twitch_channel",
            "openai_api_key",
        ):
            if not getattr(self, field_name):
                missing.append(field_name.upper())
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {joined}")
