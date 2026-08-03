import re
import sys
from datetime import timedelta
from io import TextIOWrapper
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class LevelConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    sink: Path | TextIOWrapper | Literal["stderr", "stdout"]
    rotation: Optional[str | int | timedelta] = None
    retention: Optional[str | int | timedelta] = None
    format: Optional[str] = None
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
            # Clean string for easier regex matching
            cleaned = value.strip().lower()

            # Pattern matches: "10 mb", "1 week", "2b", "12:00", or raw digits "500"
            pattern = r"^\d+\s*(kb|mb|gb|b|bytes?|days?|hours?|minutes?|seconds?|weeks?|months?)?$|^([01]\d|2[0-3]):([0-5]\d)$"

            if not re.match(pattern, cleaned):
                raise ValueError(f"Invalid Loguru format: '{value}'")
            return value

        raise ValueError("Must be a string, integer, or timedelta")


class LoggingConfig(BaseModel):
    # Console
    stdout_conf: Optional[LevelConfig] = None
    stderr_conf: Optional[LevelConfig] = None

    # Files
    debug_conf: Optional[LevelConfig] = None
    info_conf: Optional[LevelConfig] = None
    warning_conf: Optional[LevelConfig] = None
    error_conf: Optional[LevelConfig] = None
    critical_conf: Optional[LevelConfig] = None
