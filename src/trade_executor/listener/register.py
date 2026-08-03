from .telegram import TelegramListener

def get_listener(name: str):
    __registry__ = {
        "telegram": TelegramListener
    }

    return __registry__.get(name.lower())