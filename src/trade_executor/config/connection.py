from typing import Any

from pydantic import BaseModel, field_validator
from pydantic.config import ConfigDict


class TelegramConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    api_id: int
    api_hash: str
    channels: list[str | int]
    session_name: str = "trade_executor"

    @field_validator("channels", mode="after")
    @classmethod
    def normalize_channels(cls, channels: list[str | int]) -> list[str | int]:
        normalized: list[str | int] = []
        for channel in channels:
            if isinstance(channel, str):
                normalized.append(("" if channel.startswith("@") else "@") + channel)
            elif isinstance(channel, int):
                normalized.append(-channel if channel > 0 else channel)
        return normalized

    @field_validator("api_id", mode="before")
    @classmethod
    def coerce_api_id(cls, value: Any) -> int:
        return int(value)

