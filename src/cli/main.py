import asyncio
import os
from pathlib import Path
from typing import Annotated, Optional

import dotenv
import typer
from loguru import logger

from trade_executor.config import all_config_import
from trade_executor.utils import LevelConfig, LoggingConfig, setup_logging

app = typer.Typer(
    name="tse",
    help="Trade Signal Executor — autonomous trade execution from Telegram signals.",
    no_args_is_help=True,
)


@app.command()
def monitor(
    config_dir: Annotated[
        Path, typer.Option("--config-dir", "-c", help="Path to the config directory.")
    ] = Path("./configs"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Skip MT5 executor initialization.")
    ] = False,
    symbol: Annotated[
        Optional[str], typer.Option("--symbol", "-s", help="Override default trading symbol.")
    ] = None,
    max_lot_size: Annotated[
        Optional[float], typer.Option("--max-lot-size", help="Override maximum lot size.")
    ] = None,
    log_level: Annotated[
        Optional[str], typer.Option("--log-level", "-l", help="Override log level (DEBUG/INFO/WARNING/ERROR).")
    ] = None,
):
    """Start the Telegram listener → LLM parser → MT5 executor pipeline."""
    dotenv.load_dotenv()

    configs = all_config_import(str(config_dir), True, **os.environ)

    # Apply log-level override
    if log_level is not None:
        configs.setdefault("logger", {})["level"] = log_level.upper()

    stdout_level = LevelConfig(**configs["logger"])
    logging_config = LoggingConfig(stdout_conf=stdout_level)
    setup_logging(logging_config)

    if os.environ.get("USE_LLM", "false").lower() == "true":
        from cli.backends.ai import run_ai_backend

        asyncio.run(
            run_ai_backend(
                configs,
                dry_run=dry_run,
                symbol_override=symbol,
                lot_override=max_lot_size,
            )
        )
    else:
        logger.warning("USE_LLM is not enabled. Nothing to run.")


@app.command()
def migrate(
    db_path: Annotated[
        str, typer.Option("--db-path", help="Path to the SQLite database file.")
    ] = os.environ.get("DB_PATH", "trade_executor.db"),
):
    """Run database migrations (create/update schema)."""
    dotenv.load_dotenv()

    from db import SQLiteDatabase, run_migrations

    db = SQLiteDatabase(db_path=db_path)
    db.connect()
    try:
        run_migrations(db)
        typer.echo(f"Migrations applied to {db_path}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
