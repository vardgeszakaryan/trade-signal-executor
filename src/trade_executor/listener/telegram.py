from typing import Optional

from loguru import logger
from telethon import TelegramClient, events

from trade_executor.config import TelegramConfig
from trade_executor.listener.base import (
    BaseMessageHandler,
    SignalListener,
    TelegramMessage,
)


class TelegramListener(SignalListener):
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
        async def _on_new_message(event):
            # 1. Fail early if no dynamic downstream handler is registered
            if not self._handler:
                logger.warning("Handler is not set")
                return

            reply_msg = None

            # 2. Safely fetch the parent message if it's a reply
            if event.is_reply:
                original_message = await event.get_reply_message()

                if original_message:
                    # Pass the actual message object/attributes, not the event wrapper
                    reply_msg = TelegramMessage(**original_message.to_dict())
                    logger.debug("Reply message Detected:\n{}", reply_msg)

            # 3. Dispatch the sanitized structural signal
            msg = TelegramMessage(**event.message.to_dict(), reply=reply_msg)

            if not self._handler.can_handle(msg):
                # TODO: logg Message ignored
                return


            logger.info("Message Recieved:\n{}", msg)
            await self._handler.handle(msg)

        await self._client.start()  # pyright: ignore
        logger.info("Telegram successfully initialized.")
        await self._client.run_until_disconnected()  # pyright: ignore

    async def close(self):
        if self._client:
            await self._client.disconnect()  # pyright: ignore[reportGeneralTypeIssues]
            self._client = None

        logger.info("Connection Closed")

    def attach(self, handler: BaseMessageHandler):
        if not isinstance(handler, BaseMessageHandler):
            raise TypeError(
                "Handler object must be an instance of 'BaseMessageHandler'"
            )

        self._handler = handler
        logger.debug("Handler attached: {}", handler.__class__.__name__)
