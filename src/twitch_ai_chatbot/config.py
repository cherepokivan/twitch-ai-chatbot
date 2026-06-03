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
    twitch_refresh_token: str = Field(
        default="", description="Refresh token for renewing the bot user access token"
    )
    twitch_client_id: str = Field(default="", description="Twitch application client ID")
    twitch_client_secret: str = Field(default="", description="Twitch application client secret")
    twitch_bot_nick: str = Field(default="", description="Twitch login of the bot account")
    twitch_channel: str = Field(default="", description="Streamer/channel to join without #")

    llm_provider: Literal["openai", "groq"] = Field(
        default="groq", description="LLM provider used through an OpenAI-compatible client"
    )

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str = Field(default="", description="Optional OpenAI-compatible base URL")
    openai_chat_model: str = Field(default="gpt-4.1-mini", description="LLM used for replies")
    openai_vision_model: str = Field(
        default="gpt-4.1-mini", description="Vision-capable model used to summarize frames"
    )
    openai_transcription_model: str = Field(
        default="gpt-4o-mini-transcribe", description="Audio transcription model"
    )

    groq_api_key: str = Field(default="", description="Groq API key")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")
    groq_chat_model: str = Field(default="qwen/qwen3-32b", description="Groq chat/thinking model")
    groq_vision_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        description="Groq vision model used to describe stream frames.",
    )
    groq_transcription_model: str = Field(
        default="whisper-large-v3-turbo", description="Groq speech-to-text model"
    )

    vosk_enabled: bool = Field(
        default=False,
        description="Use local Vosk speech recognition instead of OpenAI/Groq transcription",
    )
    vosk_model_path: Path = Field(default=Path("models/vosk-model-small-ru-0.22"))

    bot_persona_name: str = Field(default="Света")
    bot_persona_age: int = Field(default=22)
    bot_persona_role: str = Field(
        default=(
            "дружелюбная, немного ироничная AI-подруга стримера; отвечает коротко, "
            "живым разговорным русским языком, без токсичности и спама"
        )
    )
    bot_persona_extra: str = Field(default="")
    bot_admin_users: str = Field(
        default="ivan_cherepok",
        description="Comma-separated Twitch logins that may use admin bot commands",
    )

    read_chat: bool = Field(default=True, description="Whether the bot may use viewer chat as context")
    observe_stream: bool = Field(default=True, description="Whether to analyze video/audio from stream")
    observe_video: bool = Field(default=True, description="Whether to capture stream frames")
    observe_audio: bool = Field(default=True, description="Whether to capture stream audio")

    frame_interval_seconds: int = Field(default=5, ge=1)
    audio_interval_seconds: int = Field(default=5, ge=1)
    chat_context_messages: int = Field(default=30, ge=0, le=200)
    observation_context_items: int = Field(default=12, ge=0, le=50)
    min_seconds_between_replies: int = Field(default=8, ge=0)
    max_reply_chars: int = Field(default=420, ge=50, le=500)
    reply_probability: float = Field(default=1.0, ge=0.0, le=1.0)
    llm_trust_env: bool = Field(
        default=False,
        description="Allow OpenAI/Groq HTTP client to use HTTP_PROXY/HTTPS_PROXY env vars",
    )
    streamlink_trust_env: bool = Field(
        default=False,
        description="Allow Streamlink to use HTTP_PROXY/HTTPS_PROXY env vars",
    )
    request_timeout_seconds: int = Field(default=30, ge=5)
    log_tracebacks: bool = Field(default=False, description="Log full exception tracebacks")

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

    @field_validator("twitch_refresh_token", "twitch_client_id", "twitch_client_secret")
    @classmethod
    def strip_twitch_oauth_fields(cls, value: str) -> str:
        return value.strip()

    @property
    def active_api_key(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_api_key
        return self.openai_api_key

    @property
    def admin_usernames(self) -> set[str]:
        return {
            username.strip().lower().lstrip("@")
            for username in self.bot_admin_users.split(",")
            if username.strip()
        }

    @property
    def active_base_url(self) -> str | None:
        if self.llm_provider == "groq":
            return self.groq_base_url
        return self.openai_base_url or None

    @property
    def active_chat_model(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_chat_model
        return self.openai_chat_model

    @property
    def active_vision_model(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_vision_model
        return self.openai_vision_model

    @property
    def active_transcription_model(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_transcription_model
        return self.openai_transcription_model

    def validate_required(self) -> None:
        missing = []
        for field_name in (
            "twitch_oauth_token",
            "twitch_bot_nick",
            "twitch_channel",
        ):
            if not getattr(self, field_name):
                missing.append(field_name.upper())

        if self.llm_provider == "groq":
            if not self.groq_api_key:
                missing.append("GROQ_API_KEY")
            if self.observe_video and not self.groq_vision_model:
                missing.append("GROQ_VISION_MODEL or OBSERVE_VIDEO=false")
        elif not self.openai_api_key:
            missing.append("OPENAI_API_KEY")

        if self.observe_audio and self.vosk_enabled:
            if not self.vosk_model_path.exists():
                missing.append("VOSK_MODEL_PATH existing model directory")

        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {joined}")
