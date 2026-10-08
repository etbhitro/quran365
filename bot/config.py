"""Конфигурация проекта: читает переменные окружения из .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта (папка на уровень выше этого файла).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Загружаем .env, если он есть.
load_dotenv(ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1").strip()
TRANSLATION_EDITION = os.getenv("TRANSLATION_EDITION", "ru.kuliev").strip()
PLAN_DAYS = int(os.getenv("PLAN_DAYS", "365"))

QURAN_PATH = DATA_DIR / "quran.json"
PLAN_PATH = DATA_DIR / "plan.json"
PROGRESS_DB = DATA_DIR / "progress.db"
