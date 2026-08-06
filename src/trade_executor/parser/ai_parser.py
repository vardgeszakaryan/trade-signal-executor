import time
from pathlib import Path

from litellm.router import Router
from loguru import logger
from pydantic import BaseModel, ValidationError

from trade_executor.listener import RawMessage

from .base import DefaultParser, ModelConfig, ParsedData


class LLMClient:
    def __init__(
        self,
        router: Router,
        system_prompt: str,
    ) -> None:
        self.system_prompt = system_prompt
        self.router = router

    async def generate(
        self,
        *,
        model: str,
        content: str,
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.1,
        top_p: float = 0.9,
    ):
        """Call the LLM with ONLY the prompt + user content.

        No RawMessage/model_config fields leak into the LiteLLM call.
        """
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if response_schema is not None:
            kwargs["response_format"] = response_schema

        return await self.router.acompletion(**kwargs)


class LLMParser(DefaultParser):
    def __init__(
        self, system_prompt: str | Path, router: Router, model_config: ModelConfig
    ):
        self._router = router
        self._model_config = model_config

        self._system_prompt = (
            system_prompt
            if isinstance(system_prompt, str)
            else system_prompt.read_text()
        )

        self._client = LLMClient(self._router, self._system_prompt)

    async def parse(self, message: RawMessage) -> ParsedData:
        """Parse a Raw Telegram message and return a ParsedData object.

        Only the message *text* is forwarded to the LLM; the message's
        structural fields (id/date/reply/platform) are never sent.
        Response time is measured programmatically.
        """
        start_time = time.perf_counter()
        resp = await self._client.generate(
            model=self._model_config.model,
            content=message.message,
            response_schema=self._model_config.response_schema,
            temperature=self._model_config.temperature,
            top_p=self._model_config.top_p,
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        content = resp.choices[0].message.content  # pyright: ignore
        logger.debug("LLM response:\n{}", content)

        try:
            parsed = ParsedData.model_validate_json(content)
            return parsed.model_copy(update={"resp_time": elapsed_ms})
        except ValidationError:
            logger.error("Failed to validate LLM response as ParsedData:\n{}", content)
            raise

