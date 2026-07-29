import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "rzd_bot.db"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "3"))
