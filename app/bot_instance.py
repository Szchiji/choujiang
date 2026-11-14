from aiogram import Bot

_bot: Bot | None = None


def set_bot(bot: Bot):
    """由 main.py 注入全局 Bot 实例，供 Web 路由使用"""
    global _bot
    _bot = bot


def get_bot() -> Bot | None:
    return _bot
