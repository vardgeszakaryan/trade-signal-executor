from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from trade_executor.parser import ParsedData


## Pydantic Models
class TradeOrder(BaseModel):
    id: int = Field(
        description="ID of message (Telegram msg_id). Used to look up MT5 tickets via DB."
    )
    order: ParsedData


## Abstractions
class TradeExecutor(ABC):
    @abstractmethod
    def place_order(self, order: TradeOrder, symbol: str, order_repo=None): ...

    @abstractmethod
    def close_connection(self): ...
