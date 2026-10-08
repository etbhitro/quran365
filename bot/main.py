"""Telegram-бот «Коран за 365 дней».

Запуск:  python -m bot.main
Перед первым запуском: python scripts/build_plan.py  (генерирует data/*.json)
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import checker, plan, progress
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
        "\n\n🎤 Запиши голосовое с чтением этих аятов — я распознаю и укажу на ошибки.\n"
        "Команды: /today /next /progress /day N"
    )
    return header + body + footer


# --- Команды -----------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    day = progress.get_current_day(user_id)
    greeting = (
        "Ассаламу алейкум! 🌙\n\n"
        "Я помогу заучивать Коран по плану на 365 дней. Каждый день — "
        "небольшой отрывок. Ты читаешь его вслух, записываешь голосовое, "
        "а я распознаю речь и показываю, где есть расхождения с текстом.\n"
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


# --- Обработка аудио ---------------------------------------------------------


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    day = progress.get_current_day(user_id)

    if not checker.transcription_available():
        await update.message.reply_text(
            "🎧 Я получил голосовое, но распознавание выключено "
            "(не задан OPENAI_API_KEY). Добавь ключ в .env — и я смогу "
            "проверять чтение."
        )
        return

    try:
        expected = plan.arabic_text_for_day(day)
    except plan.DataNotBuilt:
        await update.message.reply_text(
            "⚠️ Сначала сгенерируй данные: python scripts/build_plan.py"
        )
        return

    status = await update.message.reply_text("🎧 Слушаю и распознаю…")

    voice = update.message.voice or update.message.audio
    tg_file = await voice.get_file()
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "voice.ogg"
        await tg_file.download_to_drive(custom_path=str(audio_path))
        try:
            result = checker.check_recitation(str(audio_path), expected)
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка распознавания")
            await status.edit_text(f"Не получилось распознать аудио: {exc}")
            return

    progress.record_attempt(user_id, day, result.accuracy)

    percent = round(result.accuracy * 100)
    if result.accuracy >= 0.95:
        verdict = "🎉 Отлично! Почти идеально."
    elif result.accuracy >= 0.8:
        verdict = "👍 Хорошо, есть мелкие неточности."
    else:
        verdict = "📚 Стоит повторить — заметны расхождения."

    msg = f"<b>Совпадение: {percent}%</b>\n{verdict}\n"
    if result.diff_lines:
        shown = result.diff_lines[:15]
        msg += "\n<b>Что заметил:</b>\n" + "\n".join(shown)
        if len(result.diff_lines) > len(shown):
            msg += f"\n… и ещё {len(result.diff_lines) - len(shown)} замечаний."
    msg += f"\n\n<b>Распознанный текст:</b>\n<i>{result.transcript}</i>"
    if result.accuracy >= 0.8:
        msg += "\n\nГотов идти дальше? Жми /next"

    await status.edit_text(msg, parse_mode=ParseMode.HTML)


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
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    return app


def main() -> None:
    app = build_application()
    log.info("Бот запущен. Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
