from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from trade_executor.parser import ParsedData


## Pydantic Models
class TradeOrder(BaseModel):
    id: int = Field(
        description="ID of message, saved in comment. Enables later cancelation and editing."
    )
    order: ParsedData


## Abstractions
class TradeExecutor:
    @abstractmethod
    def place_order(self): ...

    @abstractmethod
    def close_connection(self): ...
