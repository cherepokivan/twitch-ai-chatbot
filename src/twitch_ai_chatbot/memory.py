from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Iterable


@dataclass(frozen=True)
class ChatLine:
    author: str
    text: str
    timestamp: datetime

    def format(self) -> str:
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.author}: {self.text}"


@dataclass(frozen=True)
class Observation:
    kind: str
    text: str
    timestamp: datetime

    def format(self) -> str:
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.kind}: {self.text}"


class RollingMemory:
    def __init__(self, chat_limit: int, observation_limit: int) -> None:
        self._chat: Deque[ChatLine] = deque(maxlen=chat_limit)
        self._observations: Deque[Observation] = deque(maxlen=observation_limit)

    def add_chat(self, author: str, text: str) -> None:
        if self._chat.maxlen == 0:
            return
        self._chat.append(ChatLine(author=author, text=text, timestamp=_now()))

    def add_observation(self, kind: str, text: str) -> None:
        if self._observations.maxlen == 0 or not text.strip():
            return
        self._observations.append(Observation(kind=kind, text=text.strip(), timestamp=_now()))

    def chat_context(self) -> Iterable[str]:
        return (line.format() for line in self._chat)

    def observation_context(self) -> Iterable[str]:
        return (item.format() for item in self._observations)


def _now() -> datetime:
    return datetime.now(timezone.utc)
