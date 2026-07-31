import asyncio
from typing import Optional, Type

from telethon import TelegramClient, events

from trade_executor.config import TelegramConfig
from trade_executor.listener.base import (
    BaseMessageHandler,
    SingalListener,
    TelegramMessage,
)


class TelegramListener(SingalListener):
    def __init__(self, config: TelegramConfig):
        self._config = config
        self._client: Optional[TelegramClient] = None
        self._handler: Optional[BaseMessageHandler] = None

    async def start(self):
        self._client = TelegramClient(
            session=self._config.session_name,
            api_id=self._config.api_id,
            api_hash=self._config.api_hash,
        )

        @self._client.on(events.NewMessage(chats=self._config.channels))
        async def _handler(event):
            # 1. Fail early if no dynamic downstream handler is registered
            if not self._handler:
                return

            reply_msg = None

            # 2. Safely fetch the parent message if it's a reply
            if event.is_reply:
                original_message = await event.get_reply_message()

                if original_message:
                    # Pass the actual message object/attributes, not the event wrapper
                    reply_msg = TelegramMessage(**original_message.to_dict())

            # 3. Dispatch the sanitized structural signal
            msg = TelegramMessage(**event.message.to_dict(), reply=reply_msg)

            if not self._handler.can_handle(msg):
                # TODO: logg Message ignored
                return

            await self._handler.handle(msg)

        await self._client.start()  # pyright: ignore
        print("Telegram listener running. Press Ctrl+C to stop.")
        await self._client.run_until_disconnected()  # pyright: ignore

    async def close(self):
        if self._client:
            await self._client.disconnect()  # pyright: ignore[reportGeneralTypeIssues]
            self._client = None

    def attach(self, handler: Type[BaseMessageHandler]):
        if not issubclass(handler, BaseMessageHandler):
            raise ValueError(
                "Handler object must be an instance of 'BaseMessageHandler'"
            )

        self._handler = handler()
