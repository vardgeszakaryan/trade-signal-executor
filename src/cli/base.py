from typing import Literal

from pydantic import BaseModel

class TradeConfig(BaseModel):
    parser_type: Literal["llm"]
    max_lot_size: float
    