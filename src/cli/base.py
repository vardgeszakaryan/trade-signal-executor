from typing import Literal

from pydantic import BaseModel

class TradeConfig(BaseModel):
    parser_type: Literal["llm"]
    max_lot_size: float = 0.03
    default_symbol: str = "XAUUSDm"
    cancel_strategy: str = "manual"