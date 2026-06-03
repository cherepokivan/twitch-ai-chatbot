from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import BotSettings

logger = logging.getLogger(__name__)

TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


async def ensure_valid_twitch_token(settings: BotSettings, env_path: Path = Path(".env")) -> None:
    """Validate the Twitch user token and refresh it when Twitch rejects it."""
    try:
        validation = await asyncio.to_thread(
            _validate_access_token, _token_for_http(settings.twitch_oauth_token)
        )
        _validate_token_login(settings, validation)
        logger.info("Twitch OAuth token is valid for %s", validation.get("login", "unknown"))
        return
    except HTTPError as exc:
        if exc.code != 401:
            raise
        logger.info("Twitch OAuth token is invalid or expired; refreshing it")

    _require_refresh_settings(settings)
    tokens = await asyncio.to_thread(_refresh_access_token, settings)
    access_token = tokens.get("access_token", "").strip()
    refresh_token = tokens.get("refresh_token", "").strip()
    if not access_token or not refresh_token:
        raise RuntimeError("Twitch refresh response did not include both access_token and refresh_token")

    settings.twitch_oauth_token = f"oauth:{access_token}"
    settings.twitch_refresh_token = refresh_token
    validation = await asyncio.to_thread(_validate_access_token, access_token)
    _validate_token_login(settings, validation)
    _update_env_file(
        env_path,
        {
            "TWITCH_OAUTH_TOKEN": settings.twitch_oauth_token,
            "TWITCH_REFRESH_TOKEN": settings.twitch_refresh_token,
        },
    )
    logger.info("Twitch OAuth token refreshed and saved to %s", env_path)


def _validate_access_token(access_token: str) -> dict[str, Any]:
    request = Request(
        TWITCH_VALIDATE_URL,
        headers={"Authorization": f"OAuth {access_token}"},
        method="GET",
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Twitch OAuth URL
        return json.loads(response.read().decode("utf-8"))


def _refresh_access_token(settings: BotSettings) -> dict[str, Any]:
    form = urlencode(
        {
            "client_id": settings.twitch_client_id,
            "client_secret": settings.twitch_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": settings.twitch_refresh_token,
        }
    ).encode("utf-8")
    request = Request(
        TWITCH_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Twitch OAuth URL
        return json.loads(response.read().decode("utf-8"))


def _require_refresh_settings(settings: BotSettings) -> None:
    missing = []
    if not settings.twitch_refresh_token:
        missing.append("TWITCH_REFRESH_TOKEN")
    if not settings.twitch_client_id:
        missing.append("TWITCH_CLIENT_ID")
    if not settings.twitch_client_secret:
        missing.append("TWITCH_CLIENT_SECRET")
    if missing:
        raise ValueError(
            "Cannot refresh Twitch token; missing environment variables: " + ", ".join(missing)
        )


def _validate_token_login(settings: BotSettings, validation: dict[str, Any]) -> None:
    token_login = str(validation.get("login", "")).lower()
    if not token_login:
        return
    if token_login != settings.twitch_bot_nick:
        raise ValueError(
            "Twitch token belongs to "
            f"'{token_login}', but TWITCH_BOT_NICK is '{settings.twitch_bot_nick}'. "
            "Create the token while logged into the bot account, or change TWITCH_BOT_NICK."
        )


def _token_for_http(token: str) -> str:
    return token.removeprefix("oauth:").strip()


def _update_env_file(env_path: Path, values: dict[str, str]) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(values)
    updated_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            updated_lines.append(f"{key}={remaining.pop(key)}")
        else:
            updated_lines.append(line)

    for key, value in remaining.items():
        updated_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
