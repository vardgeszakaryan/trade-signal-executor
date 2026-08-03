import os
from pathlib import Path
from typing import Any

from litellm.router import Router
from loguru import logger

from cli.base import TradeConfig
from trade_executor.config import TelegramConfig, all_config_import
from trade_executor.listener import BaseMessageHandler, RawMessage, get_listener
from trade_executor.parser import get_parser
from trade_executor.parser.base import ModelConfig, ParsedData


class MessageHandler(BaseMessageHandler):
    def __init__(self, config: TradeConfig, model_config: ModelConfig, router: Router):
        self.config = config
        self.model_config = model_config
        self.router = router
        self.parser = get_parser(self.config.parser_type)(
            system_prompt=self.model_config.system_prompt,
            router=router,
            model_config=model_config,
        )

    def can_handle(self, msg_obj: RawMessage) -> bool:
        return msg_obj.message is not None

    async def handle(self, msg_obj: RawMessage):
        # 1. Message is received
        # 2. Parsed
        parsed: ParsedData = await self.parser.parse(msg_obj)

        # 3. Send to executor (placeholder for future implementation)
        # TODO: Implement executor logic
        print(f"Parsed message: {parsed.model_dump()}")


async def run_ai_backend(CONFIGS: dict[str, Any] = None):
    # If no configs provided, load from configs directory
    if CONFIGS is None:
        # Calculate path to configs directory from current file location
        # Current file: src/cli/backends/ai.py
        # Configs directory is at the project root
        project_root = Path(__file__).parent.parent.parent.parent
        configs_path = project_root / "configs"
        CONFIGS = all_config_import(configs_path, change_vals=False)

    config_names = ["telegram", "router", "model", "trades"]

    for config in config_names:
        if not CONFIGS.get(config):
            # TODO LOG ERROR
            raise ValueError(f"Missing required config: {config}")

    # Load Router and trading config
    router = Router(**CONFIGS["router"])

    trade_config = TradeConfig(**CONFIGS["trades"])
    model_config = ModelConfig(response_schema=ParsedData, **CONFIGS["model"])

    logger.debug("Model config: {}", model_config)

    # Load Message listener
    telegram_config = TelegramConfig(
        api_id=int(os.environ["TELEGRAM_API_ID"]),
        api_hash=os.environ["TELEGRAM_API_HASH"],
        **CONFIGS["telegram"],
    )
    Listener = get_listener("telegram")(telegram_config)  # pyright: ignore
    Handler = MessageHandler(
        config=trade_config, model_config=model_config, router=router
    )

    Listener.attach(Handler)

    try:
        await Listener.start()

    finally:
        await Listener.close()