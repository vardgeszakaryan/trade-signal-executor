import asyncio
import os
from typing import Any

from litellm.router import Router
from loguru import logger

from cli.base import TradeConfig
from trade_executor.config import TelegramConfig
from trade_executor.execution import TradeExecutor, TradeOrder
from trade_executor.execution.mt5 import MT5Trader
from trade_executor.listener import BaseMessageHandler, RawMessage, get_listener
from trade_executor.parser import get_parser
from trade_executor.parser.base import ModelConfig, ParsedData, SignalAction


class MessageHandler(BaseMessageHandler):
    def __init__(
        self,
        config: TradeConfig,
        model_config: ModelConfig,
        router: Router,
        executor: TradeExecutor | None = None,
    ):
        self.config = config
        self.model_config = model_config
        self.router = router
        self.executor = executor
        self.parser = get_parser(self.config.parser_type)(
            system_prompt=self.model_config.system_prompt,
            router=router,
            model_config=model_config,
        )

    def can_handle(self, msg_obj: RawMessage) -> bool:
        return bool(msg_obj.message and msg_obj.message.strip())

    async def handle(self, msg_obj: RawMessage):
        # 1. Message is received and parsed by LLM
        parsed: ParsedData = await self.parser.parse(msg_obj)
        logger.info(
            "Parsed signal for message {}: action={}, size={}",
            msg_obj.id,
            parsed.action.value,
            parsed.size,
        )

        # 2. Check if action requires order placement
        if parsed.action in (SignalAction.IGNORE, SignalAction.UPDATE):
            logger.info("Action {} requires no order placement; skipping execution", parsed.action.value)
            return

        # 3. Enforce lot size safety rules
        effective_size = parsed.size
        if parsed.action in (SignalAction.BUY, SignalAction.SELL):
            if effective_size <= 0:
                effective_size = self.config.max_lot_size
                logger.info("Signal size was 0; defaulting to max lot size {}", effective_size)
            elif effective_size > self.config.max_lot_size:
                logger.warning(
                    "Signal size {} exceeds max lot size {}; capping to {}",
                    effective_size,
                    self.config.max_lot_size,
                    self.config.max_lot_size,
                )
                effective_size = self.config.max_lot_size

        final_parsed = (
            parsed.model_copy(update={"size": effective_size})
            if effective_size != parsed.size
            else parsed
        )

        trade_order = TradeOrder(id=msg_obj.id, order=final_parsed)
        symbol = self.config.default_symbol

        # 4. Dispatch to TradeExecutor
        if self.executor is not None:
            try:
                await asyncio.to_thread(self.executor.place_order, trade_order, symbol)
                logger.info(
                    "Successfully executed trade order {} ({}) on symbol {}",
                    trade_order.id,
                    final_parsed.action.value,
                    symbol,
                )
            except Exception as exc:
                logger.error("Failed to execute trade order {}: {}", trade_order.id, exc)
        else:
            logger.info(
                "No executor configured (dry-run mode). Trade order {}: {}",
                trade_order.id,
                trade_order.model_dump(),
            )


async def run_ai_backend(configs: dict[str, Any]):
    """Wire up listener → parser → executor pipeline and start the Telegram monitor."""
    required_config_keys = ["telegram", "router", "model", "trades"]

    for key in required_config_keys:
        if not configs.get(key):
            raise ValueError(f"Missing required config: {key}")

    # Load Router and trading config
    router = Router(**configs["router"])

    trade_config = TradeConfig(**configs["trades"])
    model_config = ModelConfig(response_schema=ParsedData, **configs["model"])

    logger.debug("Model config: {}", model_config)

    # Initialize MT5 executor if credentials are provided in environment
    executor: TradeExecutor | None = None
    if (
        os.environ.get("MT5_LOGIN")
        and os.environ.get("MT5_PASSWORD")
        and os.environ.get("MT5_SERVER")
    ):
        try:
            executor = MT5Trader(
                terminal_path=os.environ.get(
                    "MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"
                ),
                login=int(os.environ["MT5_LOGIN"]),
                password=os.environ["MT5_PASSWORD"],
                server=os.environ["MT5_SERVER"],
            )
            logger.info("MT5Trader initialized successfully.")
        except Exception as exc:
            logger.error("MT5Trader initialization failed: {}", exc)
    else:
        logger.info("MT5 credentials not found in environment; running in dry-run mode.")

    # Load Message listener
    telegram_config = TelegramConfig(
        api_id=int(os.environ["TELEGRAM_API_ID"]),
        api_hash=os.environ["TELEGRAM_API_HASH"],
        **configs["telegram"],
    )
    listener = get_listener("telegram")(telegram_config)  # pyright: ignore
    handler = MessageHandler(
        config=trade_config,
        model_config=model_config,
        router=router,
        executor=executor,
    )

    listener.attach(handler)

    try:
        await listener.start()
    finally:
        await listener.close()
        if executor is not None:
            executor.close_connection()
            logger.info("MT5Trader connection closed.")