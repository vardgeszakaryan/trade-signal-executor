from __future__ import annotations

import re
import sys
from datetime import timedelta
from io import TextIOWrapper
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

_LOGURU_TIME_OR_SIZE_RE = re.compile(
    r"^\d+\s*(kb|mb|gb|b|bytes?|days?|hours?|minutes?|seconds?|weeks?|months?)?$"
    r"|^([01]\d|2[0-3]):([0-5]\d)$"
)


class LevelConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    sink: Path | TextIOWrapper | Literal["stderr", "stdout"]
    rotation: str | int | timedelta | None = None
    retention: str | int | timedelta | None = None
    format: str | None = None
    serialize: bool = False
    enqueue: bool = False
    colorize: bool = False

    @field_validator("sink", mode="before")
    @classmethod
    def handle_sys_streams(cls, value):
        # Normalize incoming values to actual stream objects for runtime convenience
        if value in ("stdout", sys.stdout):
            return sys.stdout

        if value in ("stderr", sys.stderr):
            return sys.stderr

        return Path(value) if isinstance(value, str) else value

    @field_validator("rotation", "retention")
    @classmethod
    def validate_loguru_human_time_or_size(cls, value):
        # Already valid loguru types
        if isinstance(value, (int, timedelta)):
            return value

        if isinstance(value, str):
            cleaned = value.strip().lower()

            if not _LOGURU_TIME_OR_SIZE_RE.match(cleaned):
                raise ValueError(f"Invalid Loguru format: '{value}'")
            return value

        raise ValueError("Must be a string, integer, or timedelta")


class LoggingConfig(BaseModel):
    # Console
    stdout_conf: LevelConfig | None = None
    stderr_conf: LevelConfig | None = None

    # Files
    debug_conf: LevelConfig | None = None
    info_conf: LevelConfig | None = None
    warning_conf: LevelConfig | None = None
    error_conf: LevelConfig | None = None
    critical_conf: LevelConfig | None = None

