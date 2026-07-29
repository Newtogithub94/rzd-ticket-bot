import asyncio
from datetime import datetime
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import get_user_subscriptions, delete_subscription, toggle_subscription_status
from rzd_service import check_train_tickets
from services.checker import format_ticket_notification

router = Router()

CAR_NAMES = {
    "ANY": "Любой",
    "Platzkart": "Плацкарт",
    "Compartment": "Купе",
    "SV": "СВ",
    "Sitting": "Сидячий"
}

def get_seats_label(lower_only: int, upper_only: int, no_side: int) -> str:
    if lower_only and no_side:
        return "Только нижние НЕ боковые"
    elif upper_only and no_side:
        return "Только верхние НЕ боковые"
    elif lower_only:
        return "Только нижние полки"
    elif upper_only:
        return "Только верхние полки"
    elif no_side:
        return "Любые НЕ боковые полки"
    else:
        return "Любые полки"

@router.message(F.text == "📋 Мои подписки")
@router.message(F.text == "/my")
async def list_my_subscriptions(message: types.Message):
    user_id = message.from_user.id
    subs = await get_user_subscriptions(user_id)

    if not subs:
        await message.answer(
            "📭 **У вас пока нет созданных подписок.**\n\n"
            "Нажмите **«➕ Создать подписку»**, чтобы добавить первую подписку на отслеживание билетов!",
            parse_mode="Markdown"
        )
        return

    active_cnt = sum(1 for s in subs if s['status'] == "active")
    paused_cnt = sum(1 for s in subs if s['status'] != "active")
    
    header_text = f"📋 **Ваши подписки (всего: {len(subs)} | 🟢 активных: {active_cnt} | 🔴 на паузе: {paused_cnt}):**"
    await message.answer(header_text, parse_mode="Markdown")

    for sub in subs:
        sub_id = sub['id']
        status_icon = "🟢 Активна" if sub['status'] == "active" else "🔴 На паузе"
        car_str = CAR_NAMES.get(sub['car_type'], sub['car_type'])
        seats_str = get_seats_label(
            sub['lower_seats_only'],
            sub.get('upper_seats_only', 0),
            sub.get('no_side_seats', 0)
        )
        seats_count = sub.get('min_seats_count', 1)
        
        train_no = sub.get('train_number', '')
        train_dep = sub.get('train_departure', '')
        if train_no:
            dep_str = f" (отправление ⏰ {train_dep})" if train_dep else ""
            train_str = f"№{train_no}{dep_str}"
        else:
            train_str = "Все поезда"

        d_start = sub['date']
        d_end = sub.get('date_end') or d_start
        d_display = d_start if d_start == d_end else f"с {d_start} по {d_end}"

        text = (
            f"🎫 **Подписка #{sub_id}** ({status_icon})\n\n"
            f"📍 **Маршрут:** {sub['origin_name']} ➡️ {sub['destination_name']}\n"
            f"📅 **Дата:** {d_display}\n"
            f"🛋 **Вагон:** {car_str} | 👥 **Места:** {seats_count}\n"
            f"🔽 **Полки:** {seats_str}\n"
            f"🚆 **Поезд:** {train_str}\n"
            f"🕒 **Проверено:** {sub.get('last_checked_at') or 'Еще не проверялось'}"
        )

        btn_toggle_text = "⏸ На паузу" if sub['status'] == "active" else "▶️ Включить"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить сейчас", callback_data=f"check_{sub_id}"),
                InlineKeyboardButton(text=btn_toggle_text, callback_data=f"toggle_{sub_id}")
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить подписку", callback_data=f"del_{sub_id}")
            ]
        ])

        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        await asyncio.sleep(0.1)

@router.callback_query(F.data.startswith("toggle_"))
async def callback_toggle_sub(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    new_status = await toggle_subscription_status(sub_id, user_id)

    if new_status:
        status_name = "активирована 🟢" if new_status == "active" else "поставлена на паузу 🔴"
        await callback.answer(f"Подписка #{sub_id} {status_name}")
        try:
            await callback.message.edit_text(
                f"{callback.message.text}\n\n*(Статус изменен: {status_name})*",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    else:
        await callback.answer("❌ Подписка не найдена.")

@router.callback_query(F.data.startswith("del_"))
async def callback_delete_sub(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    success = await delete_subscription(sub_id, user_id)

    if success:
        await callback.answer("🗑 Подписка удалена")
        try:
            await callback.message.edit_text(f"❌ **Подписка #{sub_id} удалена.**", parse_mode="Markdown")
        except Exception:
            pass
    else:
        await callback.answer("❌ Не удалось удалить подписку.")

@router.callback_query(F.data.startswith("check_"))
async def callback_check_now(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    subs = await get_user_subscriptions(user_id)
    target_sub = next((s for s in subs if s['id'] == sub_id), None)

    if not target_sub:
        await callback.answer("❌ Подписка не найдена.")
        return

    await callback.answer("🔍 Проверяем наличие билетов в РЖД...")
    target_date = datetime.strptime(target_sub['date'], "%Y-%m-%d").date()

    trains = await check_train_tickets(
        origin_code=target_sub['origin_code'],
        destination_code=target_sub['destination_code'],
        target_date=target_date,
        car_type_filter=target_sub['car_type'],
        lower_seats_only=bool(target_sub['lower_seats_only']),
        upper_seats_only=bool(target_sub.get('upper_seats_only', 0)),
        no_side_seats=bool(target_sub.get('no_side_seats', 0)),
        min_seats_count=target_sub.get('min_seats_count', 1),
        train_number_filter=target_sub.get('train_number', '')
    )

    if trains:
        notification_text = format_ticket_notification(target_sub, trains)
        await callback.message.reply(notification_text, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await callback.message.reply(
            f"ℹ️ **Результат проверки по подписке #{sub_id}:**\n"
            f"Мест по вашим критериям на {target_sub['date']} пока нет. Бот продолжит отслеживание!",
            parse_mode="Markdown"
        )
