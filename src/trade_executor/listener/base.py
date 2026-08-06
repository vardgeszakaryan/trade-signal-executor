from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

## Message classes


class RawMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    message: str = ""
    date: datetime
    reply: RawMessage | None = None


class TelegramMessage(RawMessage):
    platform: Literal["Telegram"] = "Telegram"

    reply: RawMessage | None = None

    @field_validator("reply", mode="before")
    @classmethod
    def validate_reply(cls, data: Any):
        if data is None:
            return None

        if isinstance(data, RawMessage):
            return data

        return dict(data)


class SignalListener(ABC):
    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    def attach(self, handler: BaseMessageHandler) -> None:
        """Register a handler class to be instantiated for incoming messages."""
        ...


class BaseMessageHandler(ABC):
    @abstractmethod
    def can_handle(self, msg_obj: RawMessage) -> bool: ...

    @abstractmethod
    async def handle(self, msg_obj: RawMessage): ...
