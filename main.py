import os
import sys
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Устанавливаем прокси для библиотек requests и rzd_api на PythonAnywhere
if not os.getenv("HTTP_PROXY"):
    if os.path.exists("/home/newnew1212") or "pythonanywhere" in os.getcwd().lower() or os.path.exists("/etc/pythonanywhere"):
        os.environ["HTTP_PROXY"] = "http://proxy.server:3128"
        os.environ["HTTPS_PROXY"] = "http://proxy.server:3128"

from config import BOT_TOKEN, CHECK_INTERVAL_MINUTES
from db import init_db
from handlers import main_router
from services.checker import check_all_subscriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("=" * 60)
        logger.error("ОШИБКА: Не указан BOT_TOKEN!")
        logger.error("Пожалуйста, укажите валидный токен от @BotFather в файле .env")
        logger.error("=" * 60)
        sys.exit(1)

    logger.info("Initializing database...")
    await init_db()

    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")

    if proxy_url:
        logger.info(f"Using HTTP Proxy: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher()
    dp.include_router(main_router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_all_subscriptions,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[bot],
        id="check_all_subscriptions"
    )
    scheduler.start()
    logger.info(f"Background ticket checker scheduled every {CHECK_INTERVAL_MINUTES} minute(s).")

    logger.info("Starting Telegram Bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped gracefully.")
