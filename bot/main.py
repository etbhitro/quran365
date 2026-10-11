"""Telegram-бот «Коран за 365 дней».

Запуск:  python -m bot.main
Перед первым запуском: python scripts/build_plan.py  (генерирует data/*.json)
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import plan, progress
from .config import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("quran365")

MAX_AYAT_IN_MESSAGE = 20  # чтобы не упереться в лимит длины сообщения Telegram


# --- Вспомогательное ---------------------------------------------------------


def _render_day(day: int) -> str:
    entry = plan.day_entry(day)
    ayat = plan.ayat_for_day(day)
    header = (
        f"📖 <b>День {day} из {plan.total_days()}</b>\n"
        f"<i>{entry['label']}</i> · аятов: {entry['count']}\n\n"
    )
    lines = []
    for a in ayat[:MAX_AYAT_IN_MESSAGE]:
        lines.append(
            f"<b>{a['surah']}:{a['ayah']}</b>  {a['text_ar']}\n"
            f"<i>{a['text_tr']}</i>"
        )
    body = "\n\n".join(lines)
    if len(ayat) > MAX_AYAT_IN_MESSAGE:
        body += f"\n\n… и ещё {len(ayat) - MAX_AYAT_IN_MESSAGE} аят(ов)."
    footer = (
        "\n\n✅ Выучил(а) эти аяты? Отметь командой /done — я засчитаю день.\n"
        "Команды: /today /next /done /progress /day N"
    )
    return header + body + footer


# --- Команды -----------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    day = progress.get_current_day(user_id)
    greeting = (
        "Ассаламу алейкум! 🌙\n\n"
        "Я помогу заучивать Коран по плану на 365 дней. Каждый день — "
        "небольшой отрывок на арабском с переводом. Выучил(а) — отметь командой "
        "/done, и я засчитаю день и предложу следующий.\n"
    )
    await _send_day(update, day, prefix=greeting)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await _send_day(update, progress.get_current_day(user_id))


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    day = min(progress.get_current_day(user_id) + 1, plan.total_days())
    progress.set_current_day(user_id, day)
    await _send_day(update, day)


async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Укажи номер дня, например: /day 42")
        return
    try:
        day = int(context.args[0])
        entry_day = plan.day_entry(day)["day"]  # валидация диапазона
    except (ValueError, Exception):  # noqa: BLE001
        await update.message.reply_text(
            f"Нужно число от 1 до {plan.total_days()}."
        )
        return
    progress.set_current_day(user_id, entry_day)
    await _send_day(update, entry_day)


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    done = progress.completed_days(user_id)
    current = progress.get_current_day(user_id)
    total = plan.total_days()
    bar_len = 20
    filled = int(bar_len * done / total) if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    await update.message.reply_text(
        f"📊 <b>Твой прогресс</b>\n"
        f"{bar}\n"
        f"Пройдено дней (точность ≥80%): {done} из {total}\n"
        f"Текущий день: {current}",
        parse_mode=ParseMode.HTML,
    )


async def _send_day(update: Update, day: int, prefix: str = "") -> None:
    try:
        text = _render_day(day)
    except plan.DataNotBuilt:
        await update.message.reply_text(
            "⚠️ Данные Корана ещё не сгенерированы.\n"
            "Запусти один раз:  python scripts/build_plan.py"
        )
        return
    await update.message.reply_text(prefix + text, parse_mode=ParseMode.HTML)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отметить текущий день как выученный и перейти к следующему."""
    user_id = update.effective_user.id
    day = progress.get_current_day(user_id)
    progress.record_attempt(user_id, day, 1.0)
    total = plan.total_days()

    if day >= total:
        done = progress.completed_days(user_id)
        await update.message.reply_text(
            f"🎉 Маша’Аллах! День {day} засчитан — это последний день плана.\n"
            f"Всего пройдено дней: {done} из {total}."
        )
        return

    next_day = day + 1
    progress.set_current_day(user_id, next_day)
    done = progress.completed_days(user_id)
    await _send_day(
        update,
        next_day,
        prefix=(
            f"✅ День {day} засчитан! Пройдено: {done} из {total}.\n"
            f"Следующее задание 👇\n\n"
        ),
    )


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приём голосовых пока отключён — аудио-проверка появится позже."""
    await update.message.reply_text(
        "🎧 Спасибо за голосовое! Проверка чтения по аудио пока в разработке.\n"
        "Сейчас отмечай выученные дни командой /done."
    )


def build_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "Не задан TELEGRAM_BOT_TOKEN. Скопируй .env.example в .env "
            "и впиши токен от @BotFather."
        )
    progress.init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    return app


def main() -> None:
    app = build_application()
    log.info("Бот запущен. Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
