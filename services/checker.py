import logging
from datetime import datetime, date, timedelta
from aiogram import Bot
from db import (
    get_all_active_subscriptions,
    update_last_checked,
    increment_error_count,
    mark_error_notified,
    clear_error_notified_flag,
    get_user_settings
)
from rzd_service import check_train_tickets_for_date_range

logger = logging.getLogger(__name__)

def is_in_dnd_period(settings: dict) -> bool:
    if not settings.get("dnd_enabled", 0):
        return False
    current_hour = datetime.now().hour
    start = settings.get("dnd_start", 23)
    end = settings.get("dnd_end", 7)

    if start > end:
        # e.g. 23:00 to 07:00
        return current_hour >= start or current_hour < end
    else:
        # e.g. 01:00 to 06:00
        return start <= current_hour < end

def format_ticket_notification(sub: dict, trains: list) -> (str, float):
    orig = sub['origin_name']
    dest = sub['destination_name']
    dt_str = sub['date']
    date_end_str = sub.get('date_end') or dt_str
    
    date_display = dt_str if dt_str == date_end_str else f"с {dt_str} по {date_end_str}"

    dt_obj = datetime.strptime(dt_str, "%Y-%m-%d")
    date_formatted = dt_obj.strftime("%d.%m.%Y")
    direct_url = f"https://ticket.rzd.ru/search/trains?code0={sub['origin_code']}&code1={sub['destination_code']}&dt0={date_formatted}"

    msg = f"🎉 **НАЙДЕНЫ БИЛЕТЫ РЖД!** 🎉\n\n"
    msg += f"📍 **Маршрут:** {orig} ➡️ {dest}\n"
    msg += f"📅 **Дата:** {date_display}\n\n"
    msg += "🚆 **Доступные поезда и места:**\n"
    
    overall_min_price = float('inf')

    for tr in trains[:6]:
        msg += f"\n• **Поезд №{tr['train_number']}** ({tr['train_name']})\n"
        if tr.get('date'):
            msg += f"  📅 Дата: {tr['date']}\n"
        if tr['departure']:
            dep_fmt = tr['departure'].replace("T", " ")[:16]
            msg += f"  ⏰ Отправление: {dep_fmt}\n"
        
        for car in tr['cars']:
            min_p = float(car['min_price'])
            if min_p < overall_min_price:
                overall_min_price = min_p

            seats_info = f"всего {car['total_seats']}"
            if car['lower_seats'] > 0:
                seats_info += f" (нижних: {car['lower_seats']})"
            msg += f"  🛋 **{car['type']}**: {seats_info} — от {int(min_p)} ₽\n"

    last_price = sub.get('last_seen_min_price')
    if last_price and overall_min_price < last_price:
        diff = int(last_price - overall_min_price)
        msg += f"\n🔥 **ЦЕНА СНИЗИЛАСЬ на {diff} ₽!** (была от {int(last_price)} ₽)\n"

    msg += f"\n🔗 [Оформить билет на сайте РЖД]({direct_url})"
    return msg, (overall_min_price if overall_min_price != float('inf') else 0.0)

def format_error_notification(sub: dict, is_subsequent: bool = False) -> str:
    orig = sub['origin_name']
    dest = sub['destination_name']
    dt_str = sub['date']

    tag = "(Повторный сигнал без звука)" if is_subsequent else ""
    msg = (
        f"⚠️ **УВЕДОМЛЕНИЕ: СБОЙ СВЯЗИ С РЖД** {tag}\n\n"
        f"Бот не получил ответа от сервера РЖД по подписке **#{sub['id']}** "
        f"({orig} ➡️ {dest} на {dt_str}).\n\n"
        f"🔹 **Причина:** возможная капча РЖД, перегрузка или сбой связи.\n"
        f"🔹 **Что делает бот:** опрос продолжается каждую минуту. "
        f"Как только доступ восстановится, вы сразу получите сообщение о восстановлении!"
    )
    return msg

def format_recovery_notification(sub: dict) -> str:
    orig = sub['origin_name']
    dest = sub['destination_name']
    dt_str = sub['date']

    msg = (
        f"✅ **СВЯЗЬ С РЖД ВОССТАНОВЛЕНА!**\n\n"
        f"Сервер РЖД снова ответил по подписке **#{sub['id']}** ({orig} ➡️ {dest} на {dt_str}).\n"
        f"Бот возобновил штатную проверку свободных мест."
    )
    return msg

async def check_all_subscriptions(bot: Bot):
    logger.info("Running background check for active ticket subscriptions...")
    try:
        active_subs = await get_all_active_subscriptions()
        if not active_subs:
            logger.info("No active subscriptions to check.")
            return

        now_datetime = datetime.now()
        now_str = now_datetime.strftime("%Y-%m-%d %H:%M:%S")

        for sub in active_subs:
            sub_id = sub['id']
            user_id = sub['user_id']
            
            try:
                dt_start = datetime.strptime(sub['date'], "%Y-%m-%d").date()
                dt_end_str = sub.get('date_end') or sub['date']
                dt_end = datetime.strptime(dt_end_str, "%Y-%m-%d").date()

                if dt_end < date.today():
                    logger.info(f"Subscription #{sub_id} date {dt_end_str} has passed. Skipping.")
                    continue

                trains = await check_train_tickets_for_date_range(
                    origin_code=sub['origin_code'],
                    destination_code=sub['destination_code'],
                    date_start=dt_start,
                    date_end=dt_end,
                    car_type_filter=sub['car_type'],
                    lower_seats_only=bool(sub['lower_seats_only']),
                    upper_seats_only=bool(sub.get('upper_seats_only', 0)),
                    no_side_seats=bool(sub.get('no_side_seats', 0)),
                    min_seats_count=sub.get('min_seats_count', 1),
                    train_number_filter=sub.get('train_number', '')
                )

                # Connection successful! Check if recovery message needed
                was_error_active = await clear_error_notified_flag(sub_id)
                if was_error_active:
                    recovery_msg = format_recovery_notification(sub)
                    try:
                        await bot.send_message(chat_id=user_id, text=recovery_msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Failed to send recovery message to user {user_id}: {e}")

                min_p = 0.0
                if trains:
                    notification_text, min_p = format_ticket_notification(sub, trains)
                    
                    # Check DND period
                    user_sett = await get_user_settings(user_id)
                    in_dnd = is_in_dnd_period(user_sett)

                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=notification_text,
                            parse_mode="Markdown",
                            disable_web_page_preview=True,
                            disable_notification=in_dnd
                        )
                    except Exception as send_err:
                        logger.error(f"Failed to send Telegram message to user {user_id}: {send_err}")

                await update_last_checked(sub_id, now_str, min_price=min_p if trains else None)

            except Exception as sub_err:
                logger.error(f"Error checking subscription #{sub_id}: {sub_err}")
                err_count = await increment_error_count(sub_id)
                
                # Error notification logic:
                # First alert after 3 consecutive failures.
                # Repeat every 30 minutes SILENTLY (disable_notification=True).
                last_notified_str = sub.get('last_error_notified_at')
                should_notify = False
                is_subsequent = False
                
                if err_count >= 3:
                    if not last_notified_str:
                        should_notify = True
                        is_subsequent = False
                    else:
                        last_notified_dt = datetime.strptime(last_notified_str, "%Y-%m-%d %H:%M:%S")
                        if now_datetime - last_notified_dt >= timedelta(minutes=30):
                            should_notify = True
                            is_subsequent = True

                if should_notify:
                    await mark_error_notified(sub_id, now_str)
                    err_text = format_error_notification(sub, is_subsequent=is_subsequent)
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=err_text,
                            parse_mode="Markdown",
                            disable_notification=is_subsequent  # Silent notification for repeats!
                        )
                    except Exception as e:
                        logger.error(f"Could not send error notification to user {user_id}: {e}")

    except Exception as e:
        logger.error(f"Global error in check_all_subscriptions: {e}")
