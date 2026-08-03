from typing import Any, Iterable, Union

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
    def vlaidate_channel(cls, data: Any) -> Any:
        new_data = []

        for channel in data:
            if isinstance(channel, str):
                new_data.append(("" if channel.startswith("@") else "@") + channel)

            elif isinstance(channel, int):
                new_data.append(-channel if channel > 0 else channel)

        return new_data

    @field_validator("api_id", mode="before")
    @classmethod
    def check_id(cls, data: Any) -> Any:
        if isinstance(data, int):
            return data

        return int(data)
