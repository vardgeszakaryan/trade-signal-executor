from loguru import logger

from .ai_parser import LLMParser


def get_parser(name: str):
    __registry__ = {"llm": LLMParser}

    logger.debug(f"{name} was selected")
    return __registry__.get(name.lower())
