from typing import Any, Iterable

from pydantic import BaseModel, field_validator
from pydantic.config import ConfigDict


class TelegramConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    api_id: int
    api_hash: str
    session_name: str = "trade_executor"
    channels: list[int]

    @field_validator("api_id", mode="before")
    def check_id(cls, data: Any) -> Any:
        if isinstance(data, int):
            return data

        return int(data)

    @field_validator("channels", mode="before")
    def check_channels(cls, data: Any) -> Any:
        try:
            return [int(item) for item in data]

        except ValueError as ex:
            raise ex
