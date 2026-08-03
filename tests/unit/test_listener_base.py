from datetime import datetime

import pytest
from pydantic import ValidationError

from trade_executor.listener.base import (
    BaseMessageHandler,
    RawMessage,
    SignalListener,
    TelegramMessage,
)


class TestRawMessage:
    def test_default_message_creation(self):
        now = datetime.now()
        msg = RawMessage(
            id=1,
            message="Hello World",
            date=now,
        )
        assert msg.id == 1
        
        assert msg.message == "Hello World"
        assert msg.date == now
        assert msg.reply is None

    def test_default_message_immutability(self):
        msg = RawMessage(
            id=1,
            message="Test",
            date=datetime.now(),
        )
        with pytest.raises(ValidationError):
            msg.message = "Changed"  # type: ignore


class TestTelegramMessage:
    @pytest.fixture
    def base_message_data(self):
        return {
            "id": 10,
            "message": "Buy BTC",
            "date": datetime.now(),
        }

    def test_telegram_message_defaults(self, base_message_data):
        msg = TelegramMessage(**base_message_data)
        assert msg.platform == "Telegram"

    def test_validate_reply_from_dict(self, base_message_data):
        reply_dict = {
            "id": 1,
            "message": "Original signal",
            "date": datetime.now(),
        }
        msg = TelegramMessage(**base_message_data, reply=reply_dict)  # type: ignore
        assert msg.reply is not None
        assert msg.reply.message == "Original signal"

    def test_validate_reply_from_instance(self, base_message_data):
        reply_obj = RawMessage(
            id=2,
            message="Parent msg",
            date=datetime.now(),
        )
        msg = TelegramMessage(**base_message_data, reply=reply_obj)
        assert msg.reply == reply_obj


class TestAbstractClasses:
    def test_cannot_instantiate_signal_listener(self):
        with pytest.raises(TypeError):
            SignalListener()  # type: ignore

    def test_cannot_instantiate_base_message_handler(self):
        with pytest.raises(TypeError):
            BaseMessageHandler()  # type: ignore
