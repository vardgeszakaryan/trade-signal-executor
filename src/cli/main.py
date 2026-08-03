import asyncio
import os
from pathlib import Path

import dotenv

from trade_executor.config import all_config_import
from trade_executor.utils import LevelConfig, LoggingConfig, setup_logging

dotenv.load_dotenv()

# First load all configs
configs_path = "./configs"
CONFIGS = all_config_import(configs_path, True, **os.environ)

# Setting up logger
stdconf = LevelConfig(**CONFIGS["logger"])
logging_conf = LoggingConfig(stdout_conf=stdconf)

setup_logging(logging_conf)


async def main(CONFIGS: dict):
    if os.environ.get("USE_LLM", "false").lower() == "true":
        from cli.backends.ai import run_ai_backend

        await run_ai_backend(CONFIGS)


if __name__ == "__main__":
    asyncio.run(main(CONFIGS))
