import logging
from pathlib import Path
from loguru import logger
import litellm  # Explicitly disable litellm's built-in noise

from .base import LevelConfig, LoggingConfig


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def silence_noisy_loggers() -> None:
    """Force all standard logging loggers to pass through InterceptHandler

    and remove pre-attached library handlers.
    """
    # 1. Tame LiteLLM specific noise
    litellm.suppress_debug_info = True
    litellm.set_verbose = False

    # 2. Override noisy external loggers explicitly if you want to cap their level
    noisy_libs = ["litellm", "httpx", "httpcore", "urllib3", "asyncio"]
    for lib in noisy_libs:
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(logging.WARNING)

    # 3. Strip all pre-existing handlers from existing loggers and force propagation
    for name in logging.root.manager.loggerDict:
        mod_logger = logging.getLogger(name)
        mod_logger.handlers = []
        mod_logger.propagate = True


def setup_logging(config: LoggingConfig):
    if not isinstance(config, LoggingConfig):
        raise TypeError("Provided config is not a valid LoggingConfig object.")

    logger.remove()

    for field_name in LoggingConfig.model_fields:
        conf: LevelConfig = getattr(config, field_name)

        if conf is None:
            continue

        kwargs = {
            key: value
            for key, value in conf.__dict__.items()
            if value is not None and not key.startswith("_")
        }

        logger.add(**kwargs)
        logger.info("Configured {}", field_name)

    # Reroute root logger
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Nuke third-party logger overrides
    silence_noisy_loggers()