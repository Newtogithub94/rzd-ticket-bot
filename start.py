from datetime import datetime, date
from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from db import register_user

router = Router()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Создать подписку")],
            [KeyboardButton(text="📋 Мои подписки"), KeyboardButton(text="ℹ️ Справка")]
        ],
        resize_keyboard=True
    )

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await register_user(user.id, user.username)
    
    welcome_text = (
        f"👋 **Привет, {user.first_name}!**\n\n"
        "Я бот для отслеживания билетов РЖД. 🚆\n\n"
        "Я могу регулярно проверять наличие нужных билетов на выбранный рейс "
        "и сразу прислать вам уведомление, как только освободится место!\n\n"
        "Используйте кнопки меню ниже для управления подписками."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.message(Command("help"))
@router.message(lambda msg: msg.text == "ℹ️ Справка")
async def cmd_help(message: types.Message):
    help_text = (
        "ℹ️ **Как работать с ботом:**\n\n"
        "1. Нажмите **«➕ Создать подписку»**.\n"
        "2. Укажите станцию отправления и прибытия (бот сам найдет коды РЖД).\n"
        "3. Выберите дату поездки (ГГГГ-ММ-ДД).\n"
        "4. Выберите тип вагона (*Плацкарт, Купе, СВ, Сидячий*) и тип полок (*только нижние* при необходимости).\n"
        "5. Бот будет автоматически проверять наличие билетов и пришлет сообщение, как только они появятся!\n\n"
        "В разделе **«📋 Мои подписки»** вы можете отключать или удалять ненужные подписки."
    )
    await message.answer(help_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.message(Command("server"))
async def cmd_server(message: types.Message):
    text = (
        "🌐 **СТАТУС СЕРВЕРА**\n\n"
        "✅ Бот работает в облаке **Render.com** (24/7).\n"
        "🟢 Все системы функционируют в штатном режиме. Продление не требуется!"
    )
    await message.answer(text, parse_mode="Markdown")
