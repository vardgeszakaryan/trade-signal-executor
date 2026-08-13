from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.fields import Field

from trade_executor.listener import RawMessage


## ValidationModels
class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    CANCEL = "CANCEL"
    IGNORE = "IGNORE"
    UPDATE = "UPDATE"


class PriceSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: list[float] = Field(description="Multiple Prices are supported")
    unit: Literal["pips", "price"]
    type: Literal["single", "multiple", "range"] = Field(
        description="range would be broke down into pieces and should be represented as [min, max]"
    )


class ParsedData(BaseModel):
    model_config = ConfigDict(frozen=True)

    resp_time: float = Field(default=0.0, description="Response time in milliseconds.")
    size: float = Field(description="Size is represented in lots")
    symbol: str | None = Field(default=None, description="Symbol if specified in signal (e.g. BTCUSDTm, XAUUSDm)")

    action: SignalAction
    entry: PriceSignal | None = Field(
        default=None, description="If set none market order would be made."
    )

    stop_loss: PriceSignal | None = None
    take_profit: PriceSignal | None = None


class ModelConfig(BaseModel):
    model: str
    system_prompt: str
    response_schema: type[BaseModel] | None = None
    temperature: float = 0
    top_p: float = 0.9

    @field_validator("system_prompt", mode="before")
    @classmethod
    def validate_prompt(cls, data):
        if isinstance(data, Path):
            return data.read_text()

        # YAML loads paths as plain strings; resolve a path-like string that
        # points to an existing file. Pure-text prompts pass through unchanged.
        if isinstance(data, str):
            candidate = Path(data)
            if candidate.is_file():
                return candidate.read_text()

        return data


## Protocols
class DefaultParser(ABC):
    @abstractmethod
    async def parse(self, message: RawMessage) -> ParsedData:
        """Parses Raw Telegram message and return ParsedData object."""
        ...
