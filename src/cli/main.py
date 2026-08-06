import asyncio
import os

import dotenv

from trade_executor.config import all_config_import
from trade_executor.utils import LevelConfig, LoggingConfig, setup_logging


async def run_app(configs: dict):
    """Start the AI backend if USE_LLM is enabled."""
    if os.environ.get("USE_LLM", "false").lower() == "true":
        from cli.backends.ai import run_ai_backend

        await run_ai_backend(configs)


def main():
    """Clean, synchronous entrypoint with no arguments for project.scripts."""
    dotenv.load_dotenv()

    configs = all_config_import("./configs", True, **os.environ)

    stdout_level = LevelConfig(**configs["logger"])
    logging_config = LoggingConfig(stdout_conf=stdout_level)
    setup_logging(logging_config)

    asyncio.run(run_app(configs))


if __name__ == "__main__":
    main()

