"""
设置 Bot Menu Button 为 Mini App。
用法：docker compose exec app python scripts/set_menu_button.py
"""
import asyncio
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.config import settings


async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🎯 抽奖",
                web_app=WebAppInfo(url=f"{settings.PUBLIC_HOST.rstrip('/')}/app"),
            )
        )
        print(f"✅ Menu Button 已设置：{settings.PUBLIC_HOST}/app")
    except Exception as e:
        print(f"❌ 设置失败：{e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
