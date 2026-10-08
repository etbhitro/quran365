"""Загрузка плана на 365 дней и текста Корана."""
from __future__ import annotations

import json
from functools import lru_cache

from .config import PLAN_DAYS, PLAN_PATH, QURAN_PATH


class DataNotBuilt(Exception):
    """Данные ещё не сгенерированы — нужно запустить scripts/build_plan.py."""


@lru_cache(maxsize=1)
def _quran() -> list[dict]:
    if not QURAN_PATH.exists():
        raise DataNotBuilt
    return json.loads(QURAN_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _plan() -> list[dict]:
    if not PLAN_PATH.exists():
        raise DataNotBuilt
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def total_days() -> int:
    try:
        return len(_plan())
    except DataNotBuilt:
        return PLAN_DAYS


def day_entry(day: int) -> dict:
    """Запись плана для конкретного дня (1..N)."""
    plan = _plan()
    if not 1 <= day <= len(plan):
        raise ValueError(f"День должен быть от 1 до {len(plan)}")
    return plan[day - 1]


def ayat_for_day(day: int) -> list[dict]:
    """Список аятов (с арабским текстом и переводом) на указанный день."""
    entry = day_entry(day)
    quran = _quran()
    # Глобальные индексы 1-based, срез 0-based.
    return quran[entry["from_index"] - 1 : entry["to_index"]]


def arabic_text_for_day(day: int) -> str:
    """Весь арабский текст дня одной строкой — для сравнения с распознанным аудио."""
    return " ".join(a["text_ar"] for a in ayat_for_day(day))
