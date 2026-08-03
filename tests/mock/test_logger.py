import logging
from unittest.mock import MagicMock, patch

import pytest

from trade_executor.utils.base import LevelConfig, LoggingConfig
from trade_executor.utils.logger import InterceptHandler, setup_logging


class TestInterceptHandler:
    def test_emit_known_level(self):
        handler = InterceptHandler()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Standard log message",
            args=(),
            exc_info=None,
        )

        with patch("trade_executor.utils.logger.logger") as mock_loguru:
            mock_opt = MagicMock()
            mock_loguru.opt.return_value = mock_opt
            mock_loguru.level.return_value.name = "INFO"

            handler.emit(record)

            mock_loguru.level.assert_called_once_with("INFO")
            mock_loguru.opt.assert_called_once()
            mock_opt.log.assert_called_once_with("INFO", "Standard log message")

    def test_emit_unknown_level(self):
        handler = InterceptHandler()
        record = logging.LogRecord(
            name="test_logger",
            level=99,
            pathname=__file__,
            lineno=10,
            msg="Custom level message",
            args=(),
            exc_info=None,
        )
        record.levelname = "CUSTOM_LEVEL"

        with patch("trade_executor.utils.logger.logger") as mock_loguru:
            mock_opt = MagicMock()
            mock_loguru.opt.return_value = mock_opt
            mock_loguru.level.side_effect = ValueError("Unknown level")

            handler.emit(record)

            mock_opt.log.assert_called_once_with(99, "Custom level message")


class TestSetupLogging:
    def test_setup_logging_type_error(self):
        with pytest.raises(TypeError, match="Provided config is not a valid LoggingConfig object."):
            setup_logging("invalid_type")

    @patch("trade_executor.utils.logger.logger")
    def test_setup_logging_success(self, mock_loguru):
        level_conf = LevelConfig(level="INFO", sink="stdout", format="{message}")
        config = LoggingConfig(stdout_conf=level_conf)

        setup_logging(config)

        # Asserts logger.add and logger.info were executed
        assert mock_loguru.add.called
        assert mock_loguru.info.called

    @patch("trade_executor.utils.logger.logger")
    def test_setup_logging_skips_none_configs(self, mock_loguru):
        config = LoggingConfig(stdout_conf=None, stderr_conf=None)

        setup_logging(config)

        assert not mock_loguru.add.called