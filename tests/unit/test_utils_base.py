import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from trade_executor.utils.base import LevelConfig, LoggingConfig


class TestLevelConfig:
    def test_handle_sys_streams_stdout(self):
        config = LevelConfig(level="INFO", sink="stdout", format="{message}")
        assert config.sink == sys.stdout

        config_direct = LevelConfig(level="INFO", sink=sys.stdout, format="{message}")
        assert config_direct.sink == sys.stdout

    def test_handle_sys_streams_stderr(self):
        config = LevelConfig(level="INFO", sink="stderr", format="{message}")
        assert config.sink == sys.stderr

        config_direct = LevelConfig(level="INFO", sink=sys.stderr, format="{message}")
        assert config_direct.sink == sys.stderr

    def test_handle_path_sink(self, tmp_path):
        log_file = tmp_path / "app.log"
        config = LevelConfig(level="DEBUG", sink=str(log_file), format="{message}")
        assert config.sink == log_file
        assert isinstance(config.sink, Path)

    @pytest.mark.parametrize(
        "valid_value",
        ["10 mb", "10MB", "1 week", "12:00", 1024, timedelta(days=1)],
    )
    def test_valid_rotation_and_retention(self, valid_value):
        config = LevelConfig(
            level="WARNING",
            sink="stdout",
            rotation=valid_value,
            retention=valid_value,
            format="{message}",
        )
        assert config.rotation == valid_value
        assert config.retention == valid_value

    @pytest.mark.parametrize("invalid_value", ["10 invalid_unit", "abc", "25:60"])
    def test_invalid_rotation_retention_string(self, invalid_value):
        with pytest.raises(ValidationError):
            conf = LevelConfig(
                level="ERROR",
                sink="stdout",
                rotation=invalid_value,
                format="{message}",
            )
            print(conf)

    def test_invalid_rotation_type(self):
        with pytest.raises(ValidationError):
            LevelConfig(
                level="ERROR",
                sink="stdout",
                rotation=[100],
                format="{message}",
            )


class TestLoggingConfig:
    def test_empty_config(self):
        config = LoggingConfig()
        assert config.stdout_conf is None
        assert config.stderr_conf is None

    def test_populated_config(self):
        level_conf = LevelConfig(level="INFO", sink="stdout", format="{message}")
        config = LoggingConfig(stdout_conf=level_conf)
        assert config.stdout_conf == level_conf
