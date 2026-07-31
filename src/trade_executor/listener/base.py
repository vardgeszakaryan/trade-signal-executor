from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, field_validator

## Message classes


class DefaultMessage(BaseModel):  # TelegramMessage was renamed DefaultMessage.
    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    from_id: int
    message: str
    date: datetime
    reply: Optional[DefaultMessage] = None


class TelegramMessage(DefaultMessage):
    platform: Literal["Telegram"] = "Telegram"

    from_id: int
    reply: Optional[DefaultMessage] = None

    @field_validator("reply", mode="before")
    def validate_reply(cls, data: Any):
        if data is None:
            return None

        if isinstance(data, DefaultMessage):
            return data

        return dict(data)

    @field_validator("from_id", mode="before")
    def validate_fromid(cls, data: Any):
        if isinstance(data, dict):
            return data["user_id"]

        if isinstance(data, str):
            return int(data)

        return data


class SingalListener(ABC):
    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def close(self): ...

    def attach(self, handler: Type[BaseMessageHandler]):
        """Call handler(BaseMessageHandler) for every incoming message"""
        ...


class BaseMessageHandler(ABC):
    @abstractmethod
    def can_handle(self, msg_obj: DefaultMessage) -> bool: ...

    @abstractmethod
    async def handle(self, msg_obj: DefaultMessage): ...
