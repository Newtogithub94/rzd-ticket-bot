import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from rzd_service import find_stations, get_train_schedule
from db import add_subscription
from handlers.start import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()

POPULAR_STATIONS_TEXT = (
    "💡 **Популярные станции (нажмите на слово, чтобы скопировать):**\n"
    "`Москва` • `Санкт-Петербург` • `Петрозаводск` • `Шильда` • `Орск` • `Новый Уренгой` • `Новосибирск`"
)

class SubscriptionFSM(StatesGroup):
    waiting_for_origin = State()
    selecting_origin_station = State()
    waiting_for_destination = State()
    selecting_destination_station = State()
    waiting_for_date = State()
    waiting_for_guard_decision = State()
    waiting_for_car_type = State()
    waiting_for_seats_pref = State()
    waiting_for_seats_count = State()
    waiting_for_train_number = State()

def get_cancel_button() -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="nav_cancel")]

# --- Global Navigation Callbacks ---

@router.callback_query(F.data == "nav_cancel")
async def nav_cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Подписка отменена")
    try:
        await callback.message.edit_text("❌ Создание подписки отменено. Вы вернулись в главное меню.")
    except Exception:
        pass
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())

# --- Step 1: Origin Station ---

@router.message(F.text == "➕ Создать подписку")
@router.message(F.text == "/subscribe")
async def start_subscription(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(SubscriptionFSM.waiting_for_origin)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
    await message.answer(
        f"🌆 **Шаг 1 из 7:** Введите название города или станции **отправления**\n"
        f"(например: *Москва*, *Санкт-Петербург*, *Казань*):\n\n"
        f"{POPULAR_STATIONS_TEXT}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.message(SubscriptionFSM.waiting_for_origin)
@router.message(SubscriptionFSM.selecting_origin_station)
async def process_origin_query(message: types.Message, state: FSMContext):
    query = message.text.strip()
    msg_wait = None
    try:
        msg_wait = await message.answer("🔍 Ищем станции в РЖД...")
        stations = await find_stations(query)
        if msg_wait:
            try:
                await msg_wait.delete()
            except Exception:
                pass

        if not stations:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
            await message.answer("❌ Станции по вашему запросу не найдены. Попробуйте ввести другое название:", reply_markup=keyboard)
            return

        buttons = []
        for st in stations[:8]:
            btn_text = f"{st['name']} ({st['code']})"
            callback_data = f"orig_{st['code']}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])

        buttons.append(get_cancel_button())
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await state.update_data(origin_stations=stations)
        await state.set_state(SubscriptionFSM.selecting_origin_station)
        await message.answer("📍 Выберите станцию отправления из списка (или введите другое название в чат):", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error processing origin query '{query}': {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
        await message.answer("⚠️ Ошибка при поиске станции. Попробуйте ввести еще раз:", reply_markup=keyboard)

@router.callback_query(SubscriptionFSM.selecting_origin_station, F.data.startswith("orig_"))
async def select_origin_station(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.replace("orig_", "").strip()
    data = await state.get_data()
    stations = data.get("origin_stations", [])
    
    st_obj = next((s for s in stations if str(s['code']) == code), None)
    name = st_obj['name'] if st_obj else f"Станция {code}"

    await state.update_data(origin_code=code, origin_name=name)
    await callback.answer()
    
    try:
        await callback.message.edit_text(f"✅ Станция отправления: **{name}** (код `{code}`)", parse_mode="Markdown")
    except Exception:
        pass

    await ask_destination_step(callback.message, state)

# --- Step 2: Destination Station ---

async def ask_destination_step(message: types.Message, state: FSMContext):
    await state.set_state(SubscriptionFSM.waiting_for_destination)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
    await message.answer(
        f"🏙 **Шаг 2 из 7:** Введите название города или станции **прибытия**\n"
        f"(например: *Адлер*, *Петрозаводск*, *Орск*):\n\n"
        f"{POPULAR_STATIONS_TEXT}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.message(SubscriptionFSM.waiting_for_destination)
@router.message(SubscriptionFSM.selecting_destination_station)
async def process_destination_query(message: types.Message, state: FSMContext):
    query = message.text.strip()
    msg_wait = None
    try:
        msg_wait = await message.answer("🔍 Ищем станции в РЖД...")
        stations = await find_stations(query)
        if msg_wait:
            try:
                await msg_wait.delete()
            except Exception:
                pass

        if not stations:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
            await message.answer("❌ Станции по вашему запросу не найдены. Попробуйте ввести другое название:", reply_markup=keyboard)
            return

        buttons = []
        for st in stations[:8]:
            btn_text = f"{st['name']} ({st['code']})"
            callback_data = f"dest_{st['code']}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])

        buttons.append(get_cancel_button())
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await state.update_data(destination_stations=stations)
        await state.set_state(SubscriptionFSM.selecting_destination_station)
        await message.answer("📍 Выберите станцию прибытия из списка (или введите другое название в чат):", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error processing destination query '{query}': {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
        await message.answer("⚠️ Ошибка при поиске станции. Попробуйте ввести еще раз:", reply_markup=keyboard)

@router.callback_query(SubscriptionFSM.selecting_destination_station, F.data.startswith("dest_"))
async def select_destination_station(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.replace("dest_", "").strip()
    data = await state.get_data()
    stations = data.get("destination_stations", [])
    
    st_obj = next((s for s in stations if str(s['code']) == code), None)
    name = st_obj['name'] if st_obj else f"Станция {code}"

    await state.update_data(destination_code=code, destination_name=name)
    await callback.answer()
    
    try:
        await callback.message.edit_text(f"✅ Станция прибытия: **{name}** (код `{code}`)", parse_mode="Markdown")
    except Exception:
        pass

    await ask_date_step(callback.message, state)

# --- Step 3: Travel Date ---

async def ask_date_step(message: types.Message, state: FSMContext):
    today = date.today()
    quick_dates = [
        [InlineKeyboardButton(text=f"Завтра ({(today + timedelta(days=1)).strftime('%d.%m')})", callback_data=f"dt_{(today + timedelta(days=1)).strftime('%Y-%m-%d')}")],
        [InlineKeyboardButton(text=f"Через 3 дня ({(today + timedelta(days=3)).strftime('%d.%m')})", callback_data=f"dt_{(today + timedelta(days=3)).strftime('%Y-%m-%d')}")],
        [InlineKeyboardButton(text=f"Через неделю ({(today + timedelta(days=7)).strftime('%d.%m')})", callback_data=f"dt_{(today + timedelta(days=7)).strftime('%Y-%m-%d')}")],
        get_cancel_button()
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=quick_dates)

    await state.set_state(SubscriptionFSM.waiting_for_date)
    await message.answer(
        "📅 **Шаг 3 из 7:** Введите дату поездки или диапазон дат:\n\n"
        "• Одиночная дата (например `2026-08-15`)\n"
        "• Диапазон дат (например `2026-08-15:2026-08-17`)\n\n"
        "Или выберите быстрый вариант ниже:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(SubscriptionFSM.waiting_for_date, F.data.startswith("dt_"))
async def process_quick_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str, date_end=date_str)
    await callback.answer()
    await fetch_schedule_and_check_route(callback.message, state, date_str, date_str)

@router.message(SubscriptionFSM.waiting_for_date)
async def process_text_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        if ":" in text:
            parts = text.split(":")
            d1 = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            d2 = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
            if d1 > d2:
                d1, d2 = d2, d1
            if d2 < date.today():
                await message.answer("⚠️ Даты не могут быть в прошлом!")
                return
            d1_str = d1.strftime("%Y-%m-%d")
            d2_str = d2.strftime("%Y-%m-%d")
            await state.update_data(date=d1_str, date_end=d2_str)
            await fetch_schedule_and_check_route(message, state, d1_str, d2_str)
        else:
            parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
            if parsed_date < date.today():
                await message.answer("⚠️ Дата не может быть в прошлом!")
                return
            d_str = parsed_date.strftime("%Y-%m-%d")
            await state.update_data(date=d_str, date_end=d_str)
            await fetch_schedule_and_check_route(message, state, d_str, d_str)
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[get_cancel_button()])
        await message.answer("❌ Неверный формат! Введите `YYYY-MM-DD` или `YYYY-MM-DD:YYYY-MM-DD`:", reply_markup=keyboard, parse_mode="Markdown")

async def fetch_schedule_and_check_route(message: types.Message, state: FSMContext, date_str: str, date_end_str: str):
    data = await state.get_data()
    display_d = date_str if date_str == date_end_str else f"с {date_str} по {date_end_str}"
    msg_wait = await message.answer(f"🔍 Запрашиваем расписание РЖД на **{display_d}**...", parse_mode="Markdown")

    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    trains = await get_train_schedule(data['origin_code'], data['destination_code'], target_date)
    if msg_wait:
        try:
            await msg_wait.delete()
        except Exception:
            pass

    await state.update_data(available_trains=trains)

    if not trains:
        guard_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Изменить дату поездки", callback_data="guard_date")],
            [InlineKeyboardButton(text="📍 Изменить станции", callback_data="guard_stations")],
            [InlineKeyboardButton(text="⚠️ Все равно создать подписку", callback_data="guard_continue")],
            get_cancel_button()
        ])
        await state.set_state(SubscriptionFSM.waiting_for_guard_decision)
        await message.answer(
            f"🛡 **ПРЕДОХРАНИТЕЛЬ: МАРШРУТ НЕ НАЙДЕН!**\n\n"
            f"РЖД не возвращает ни одного поезда между станцией **{data['origin_name']}** и **{data['destination_name']}** на **{display_d}**.\n\n"
            f"• Возможно, между этими станциями нет прямого ж/д сообщения.\n"
            f"• Или поезда по данному маршруту ходят в другие дни недели.\n"
            f"• Или продажи на эту дату еще не открылись.\n\n"
            f"Что вы хотите сделать?",
            reply_markup=guard_keyboard,
            parse_mode="Markdown"
        )
        return

    schedule_msg = f"✅ Дата поездки: **{display_d}**\n\n"
    schedule_msg += f"🚆 **Расписание имеющихся поездов ({len(trains)}):**\n"
    for t in trains[:10]:
        name_part = f" «{t['name']}»" if t['name'] else ""
        dep_fmt = f"⏰ {t['departure']}" if t['departure'] else "—"
        arr_fmt = f"{t['arrival']}" if t['arrival'] else "—"
        schedule_msg += f"• **Поезд №{t['number']}**{name_part} — {dep_fmt} ➡️ {arr_fmt}\n"
    if len(trains) > 10:
        schedule_msg += f"*(и еще {len(trains) - 10} поездов...)*\n"

    await message.answer(schedule_msg, parse_mode="Markdown")
    await ask_car_type_step(message, state)

@router.callback_query(SubscriptionFSM.waiting_for_guard_decision, F.data == "guard_date")
async def guard_change_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_date_step(callback.message, state)

@router.callback_query(SubscriptionFSM.waiting_for_guard_decision, F.data == "guard_stations")
async def guard_change_stations(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_subscription_from_callback(callback, state)

@router.callback_query(SubscriptionFSM.waiting_for_guard_decision, F.data == "guard_continue")
async def guard_force_continue(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.edit_text("⚠️ Продолжаем создание подписки, несмотря на отсутствие поездов в текущей выдаче.", parse_mode="Markdown")
    except Exception:
        pass
    await ask_car_type_step(callback.message, state)

# --- Step 4: Car Type ---

async def ask_car_type_step(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛋 Любой тип вагона", callback_data="car_ANY")],
        [InlineKeyboardButton(text="🛏 Плацкарт", callback_data="car_Platzkart"), InlineKeyboardButton(text="🚪 Купе", callback_data="car_Compartment")],
        [InlineKeyboardButton(text="👑 СВ / Люкс", callback_data="car_SV"), InlineKeyboardButton(text="🪑 Сидячий", callback_data="car_Sitting")],
        get_cancel_button()
    ])
    await state.set_state(SubscriptionFSM.waiting_for_car_type)
    await message.answer("🛏 **Шаг 4 из 7:** Выберите желаемый тип вагона:", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(SubscriptionFSM.waiting_for_car_type, F.data.startswith("car_"))
async def process_car_type(callback: types.CallbackQuery, state: FSMContext):
    car_type = callback.data.split("_")[1]
    await state.update_data(car_type=car_type, seat_height="any", no_side_seats=0)
    await callback.answer()
    
    car_names = {"ANY": "Любой", "Platzkart": "Плацкарт", "Compartment": "Купе", "SV": "СВ", "Sitting": "Сидячий"}
    try:
        await callback.message.edit_text(f"✅ Тип вагона: **{car_names.get(car_type, car_type)}**", parse_mode="Markdown")
    except Exception:
        pass

    await state.set_state(SubscriptionFSM.waiting_for_seats_pref)
    await send_seats_keyboard(callback.message, state)

# --- Step 5: Seats Preference ---

def get_seats_keyboard_markup(seat_height: str, no_side: int) -> InlineKeyboardMarkup:
    h_any = "✅ Любые" if seat_height == "any" else "Любые"
    h_lower = "✅ Только нижние" if seat_height == "lower" else "Только нижние"
    h_upper = "✅ Только верхние" if seat_height == "upper" else "Только верхние"

    side_icon = "☑️ [ВКЛ]" if no_side else "🔲 [ВЫКЛ]"
    side_text = f"🚫 Без боковых полок: {side_icon}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=h_lower, callback_data="st_height_lower"),
            InlineKeyboardButton(text=h_upper, callback_data="st_height_upper")
        ],
        [
            InlineKeyboardButton(text=h_any, callback_data="st_height_any")
        ],
        [
            InlineKeyboardButton(text=side_text, callback_data="st_toggle_side")
        ],
        [
            InlineKeyboardButton(text="➡️ Подтвердить выбор полок", callback_data="st_confirm")
        ],
        get_cancel_button()
    ])

async def send_seats_keyboard(message: types.Message, state: FSMContext):
    data = await state.get_data()
    seat_height = data.get("seat_height", "any")
    no_side = data.get("no_side_seats", 0)

    height_descriptions = {
        "any": "Любая полка (верхняя или нижняя)",
        "lower": "Только нижняя полка",
        "upper": "Только верхняя полка"
    }
    side_desc = "Да (без боковых)" if no_side else "Нет (включая боковые)"

    text = (
        "🔽 **Шаг 5 из 7:** Настройте параметры полок:\n\n"
        f"• **Тип полок:** {height_descriptions.get(seat_height)}\n"
        f"• **Исключить боковые:** {side_desc}\n\n"
        "*(Нажимайте кнопки ниже для переключения, затем нажмите «Подтвердить выбор»)*"
    )

    markup = get_seats_keyboard_markup(seat_height, no_side)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@router.callback_query(SubscriptionFSM.waiting_for_seats_pref, F.data.startswith("st_"))
async def process_seats_toggle(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    seat_height = data.get("seat_height", "any")
    no_side = data.get("no_side_seats", 0)

    action = callback.data

    if action.startswith("st_height_"):
        new_h = action.replace("st_height_", "")
        await state.update_data(seat_height=new_h)
        await callback.answer()
        markup = get_seats_keyboard_markup(new_h, no_side)
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass

    elif action == "st_toggle_side":
        new_side = 0 if no_side else 1
        await state.update_data(no_side_seats=new_side)
        await callback.answer("Галочка «Без боковых» переключена!")
        markup = get_seats_keyboard_markup(seat_height, new_side)
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass

    elif action == "st_confirm":
        await callback.answer()
        
        lower_only = 1 if seat_height == "lower" else 0
        upper_only = 1 if seat_height == "upper" else 0

        await state.update_data(lower_seats_only=lower_only, upper_seats_only=upper_only)

        if lower_only and no_side:
            pref_summary = "Только нижние НЕ боковые"
        elif upper_only and no_side:
            pref_summary = "Только верхние НЕ боковые"
        elif lower_only:
            pref_summary = "Только нижние полки"
        elif upper_only:
            pref_summary = "Только верхние полки"
        elif no_side:
            pref_summary = "Любые НЕ боковые полки"
        else:
            pref_summary = "Любые полки"

        try:
            await callback.message.edit_text(f"✅ Полки: **{pref_summary}**", parse_mode="Markdown")
        except Exception:
            pass

        await state.set_state(SubscriptionFSM.waiting_for_seats_count)
        await ask_seats_count_step(callback.message, state)

# --- Step 6: Seats Count ---

async def ask_seats_count_step(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 место", callback_data="scount_1"),
            InlineKeyboardButton(text="2 места в одном вагоне", callback_data="scount_2")
        ],
        [
            InlineKeyboardButton(text="3 места в одном вагоне", callback_data="scount_3"),
            InlineKeyboardButton(text="4 места в одном купе/вагоне", callback_data="scount_4")
        ],
        get_cancel_button()
    ])
    await state.set_state(SubscriptionFSM.waiting_for_seats_count)
    await message.answer("👥 **Шаг 6 из 7:** Сколько мест требуется?", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(SubscriptionFSM.waiting_for_seats_count, F.data.startswith("scount_"))
async def process_seats_count(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[1])
    await state.update_data(min_seats_count=count)
    await callback.answer()

    try:
        await callback.message.edit_text(f"✅ Количество мест: **{count}**", parse_mode="Markdown")
    except Exception:
        pass

    data = await state.get_data()
    trains = data.get("available_trains", [])

    buttons = [[InlineKeyboardButton(text="🚆 Все поезда на маршруте", callback_data="train_SKIP")]]

    trains_text_list = ""
    if trains:
        trains_text_list = "\n\n📋 **Расписание доступных рейсов:**\n"
        for t in trains[:10]:
            name_str = f" «{t['name']}»" if t['name'] else ""
            dep_fmt = f"⏰ {t['departure']}" if t['departure'] else "—"
            arr_fmt = f"{t['arrival']}" if t['arrival'] else "—"
            trains_text_list += f"• **Поезд №{t['number']}**{name_str} — {dep_fmt} (прибытие {arr_fmt})\n"

            btn_label = f"⏰ {t['departure']} | Поезд №{t['number']}" if t['departure'] else f"Поезд №{t['number']}"
            callback_data = f"trno_{t['number']}_{t['departure']}"
            buttons.append([InlineKeyboardButton(text=btn_label, callback_data=callback_data)])

    buttons.append(get_cancel_button())
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(SubscriptionFSM.waiting_for_train_number)
    await callback.message.answer(
        f"🚆 **Шаг 7 из 7:** Выберите конкретный поезд{trains_text_list}\n"
        "Выберите поезд на кнопках ниже (указано время отправления), нажмите **«Все поезда»** или введите номер поезда в чат:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# --- Step 7: Train Selection & Finish ---

@router.callback_query(SubscriptionFSM.waiting_for_train_number, F.data == "train_SKIP")
async def skip_train_number(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(train_number="", train_departure="")
    await callback.answer()
    try:
        await callback.message.edit_text("✅ Поезда: **Все поезда на маршруте**", parse_mode="Markdown")
    except Exception:
        pass
    await finish_subscription(callback.message, state, user_id=callback.from_user.id)

@router.callback_query(SubscriptionFSM.waiting_for_train_number, F.data.startswith("trno_"))
async def select_train_number(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    train_no = parts[1]
    dep_time = parts[2] if len(parts) > 2 else ""

    await state.update_data(train_number=train_no, train_departure=dep_time)
    await callback.answer()
    
    dep_info = f" (отправление ⏰ {dep_time})" if dep_time else ""
    try:
        await callback.message.edit_text(f"✅ Выбран поезд: **№{train_no}**{dep_info}", parse_mode="Markdown")
    except Exception:
        pass
    await finish_subscription(callback.message, state, user_id=callback.from_user.id)

@router.message(SubscriptionFSM.waiting_for_train_number)
async def process_train_number(message: types.Message, state: FSMContext):
    train_no = message.text.strip().upper()
    await state.update_data(train_number=train_no, train_departure="")
    await message.answer(f"✅ Выбран поезд: **№{train_no}**", parse_mode="Markdown")
    await finish_subscription(message, state, user_id=message.from_user.id)

async def finish_subscription(message: types.Message, state: FSMContext, user_id: int):
    data = await state.get_data()
    
    sub_id = await add_subscription(
        user_id=user_id,
        origin_code=data['origin_code'],
        origin_name=data['origin_name'],
        destination_code=data['destination_code'],
        destination_name=data['destination_name'],
        date_str=data['date'],
        date_end_str=data.get('date_end', data['date']),
        car_type=data['car_type'],
        lower_seats_only=data.get('lower_seats_only', 0),
        upper_seats_only=data.get('upper_seats_only', 0),
        no_side_seats=data.get('no_side_seats', 0),
        min_seats_count=data.get('min_seats_count', 1),
        train_number=data.get('train_number', ''),
        train_departure=data.get('train_departure', '')
    )

    car_names = {"ANY": "Любой", "Platzkart": "Плацкарт", "Compartment": "Купе", "SV": "СВ", "Sitting": "Сидячий"}
    car_str = car_names.get(data['car_type'], data['car_type'])
    
    lower_only = data.get('lower_seats_only', 0)
    upper_only = data.get('upper_seats_only', 0)
    no_side = data.get('no_side_seats', 0)

    if lower_only and no_side:
        seats_str = "Только нижние НЕ боковые"
    elif upper_only and no_side:
        seats_str = "Только верхние НЕ боковые"
    elif lower_only:
        seats_str = "Только нижние"
    elif upper_only:
        seats_str = "Только верхние"
    elif no_side:
        seats_str = "Любые НЕ боковые"
    else:
        seats_str = "Любые"

    train_no = data.get('train_number', '')
    dep_time = data.get('train_departure', '')
    if train_no:
        dep_str = f" (отправление ⏰ {dep_time})" if dep_time else ""
        train_str = f"№{train_no}{dep_str}"
    else:
        train_str = "Все поезда"

    d_start = data['date']
    d_end = data.get('date_end', d_start)
    d_display = d_start if d_start == d_end else f"с {d_start} по {d_end}"
    seats_cnt = data.get('min_seats_count', 1)

    summary = (
        f"🎉 **ПОДПИСКА УСПЕШНО СОЗДАНА!** (# {sub_id})\n\n"
        f"📍 **Маршрут:** {data['origin_name']} ➡️ {data['destination_name']}\n"
        f"📅 **Дата:** {d_display}\n"
        f"🛋 **Вагон:** {car_str} | 👥 **Места:** {seats_cnt}\n"
        f"🔽 **Полки:** {seats_str}\n"
        f"🚆 **Поезд:** {train_str}\n\n"
        "🔔 Бот будет регулярно проверять места и сразу пришлет вам уведомление при появлении билетов!"
    )
    await state.clear()
    await message.answer(summary, reply_markup=get_main_keyboard(), parse_mode="Markdown")
