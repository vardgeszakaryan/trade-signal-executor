import asyncio
import os
from typing import Any

from litellm.router import Router
from loguru import logger

from cli.base import TradeConfig
from db import OrderRepository, SQLiteDatabase, run_migrations
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
        order_repo: OrderRepository | None = None,
    ):
        self.config = config
        self.model_config = model_config
        self.router = router
        self.executor = executor
        self.order_repo = order_repo
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

        # Resolve signal ID: CANCEL/CLOSE/UPDATE that arrive as replies to the
        # original BUY/SELL message need the *replied-to* message's ID (that's
        # what the order was recorded under).  BUY/SELL always use their own ID.
        if (
            parsed.action in (SignalAction.CANCEL, SignalAction.CLOSE, SignalAction.UPDATE)
            and msg_obj.reply is not None
        ):
            signal_id = msg_obj.reply.id
            logger.debug(
                "Action {} is a reply; using original message id {} (not {})",
                parsed.action.value, signal_id, msg_obj.id,
            )
        else:
            signal_id = msg_obj.id

        trade_order = TradeOrder(id=signal_id, order=final_parsed)
        symbol = final_parsed.symbol or self.config.default_symbol

        # 4. Dispatch to TradeExecutor
        if self.executor is not None:
            try:
                await asyncio.to_thread(
                    self.executor.place_order, trade_order, symbol, self.order_repo
                )
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


async def run_ai_backend(
    configs: dict[str, Any],
    *,
    dry_run: bool = False,
    symbol_override: str | None = None,
    lot_override: float | None = None,
):
    """Wire up listener → parser → executor pipeline and start the Telegram monitor."""
    required_config_keys = ["telegram", "router", "model", "trades"]

    for key in required_config_keys:
        if not configs.get(key):
            raise ValueError(f"Missing required config: {key}")

    # Load Router and trading config
    router = Router(**configs["router"])

    trade_config = TradeConfig(**configs["trades"])
    model_config = ModelConfig(response_schema=ParsedData, **configs["model"])

    # Apply CLI overrides
    if symbol_override is not None:
        trade_config = trade_config.model_copy(update={"default_symbol": symbol_override})
    if lot_override is not None:
        trade_config = trade_config.model_copy(update={"max_lot_size": lot_override})

    logger.debug("Model config: {}", model_config)

    # Initialize DB + OrderRepository
    db_path = os.environ.get("DB_PATH", "trade_executor.db")
    db = SQLiteDatabase(db_path=db_path)
    db.connect()
    run_migrations(db)
    order_repo = OrderRepository(db)
    logger.info("Database initialized at {}", db_path)

    # Initialize MT5 executor if credentials are provided and not dry-run
    executor: TradeExecutor | None = None
    if not dry_run and (
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
        reason = "dry-run mode" if dry_run else "MT5 credentials not found in environment"
        logger.info("{}; running in dry-run mode.", reason)

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
        order_repo=order_repo,
    )

    listener.attach(handler)

    try:
        await listener.start()
    finally:
        await listener.close()
        db.close()
        logger.info("Database connection closed.")
        if executor is not None:
            executor.close_connection()
            logger.info("MT5Trader connection closed.")