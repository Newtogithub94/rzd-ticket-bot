import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, CHECK_INTERVAL_MINUTES
from db import init_db
from handlers import main_router
from services.checker import check_all_subscriptions

# Configure logging
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

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(main_router)

    # Initialize APScheduler for background ticket checks
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_all_subscriptions,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[bot],
        id="rzd_ticket_checker"
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
