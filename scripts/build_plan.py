"""Скачивает текст Корана и строит план на N дней.

Запуск:  python scripts/build_plan.py

Что делает:
1. Берёт арабский текст (quran-uthmani) и перевод из бесплатного API alquran.cloud.
2. Складывает все 6236 аятов по порядку мусхафа.
3. Делит их на равные (почти) части — по одной на каждый день.
4. Сохраняет data/quran.json и data/plan.json.

Данные публичные, API бесплатный: https://alquran.cloud/api
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

# Чтобы скрипт работал и из корня, и из папки scripts.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config import DATA_DIR, PLAN_DAYS, QURAN_PATH, PLAN_PATH, TRANSLATION_EDITION  # noqa: E402

API = "https://api.alquran.cloud/v1/quran/{edition}"


def fetch_edition(edition: str) -> dict:
    url = API.format(edition=edition)
    print(f"  Скачиваю: {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 200:
        raise RuntimeError(f"API вернул ошибку для {edition}: {payload}")
    return payload["data"]


def make_plan(ayat_list: list[dict], days: int) -> list[dict]:
    """Делит список аятов на `days` почти равных подряд идущих частей.

    Первые `total % days` дней получают на один аят больше, поэтому разница
    между самым большим и самым маленьким днём — не более одного аята.
    """
    total = len(ayat_list)
    if days < 1 or days > total:
        raise ValueError(f"days должно быть в диапазоне 1..{total}, получено {days}")

    base = total // days
    extra = total % days
    plan: list[dict] = []
    cursor = 0
    for day in range(1, days + 1):
        count = base + (1 if day <= extra else 0)
        chunk = ayat_list[cursor : cursor + count]
        cursor += count
        first, last = chunk[0], chunk[-1]
        plan.append(
            {
                "day": day,
                "from_index": first["index"],
                "to_index": last["index"],
                "count": len(chunk),
                "label": _label(first, last),
            }
        )
    return plan


def build() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Шаг 1/3: скачиваю арабский текст и перевод...")
    arabic = fetch_edition("quran-uthmani")
    translation = fetch_edition(TRANSLATION_EDITION)

    print("Шаг 2/3: собираю аяты...")
    ayat_list: list[dict] = []
    for sura_ar, sura_tr in zip(arabic["surahs"], translation["surahs"]):
        for ayah_ar, ayah_tr in zip(sura_ar["ayahs"], sura_tr["ayahs"]):
            ayat_list.append(
                {
                    "index": len(ayat_list) + 1,  # глобальный номер 1..6236
                    "surah": sura_ar["number"],
                    "surah_name": sura_ar["englishName"],
                    "surah_name_ar": sura_ar["name"],
                    "ayah": ayah_ar["numberInSurah"],
                    "text_ar": ayah_ar["text"],
                    "text_tr": ayah_tr["text"],
                }
            )

    total = len(ayat_list)
    print(f"  Всего аятов: {total}")

    QURAN_PATH.write_text(
        json.dumps(ayat_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Сохранил: {QURAN_PATH}")

    print(f"Шаг 3/3: делю на {PLAN_DAYS} дней...")
    plan = make_plan(ayat_list, PLAN_DAYS)

    PLAN_PATH.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Сохранил: {PLAN_PATH}")
    print("\nГотово! Теперь можно запускать бота:  python -m bot.main")


def _label(first: dict, last: dict) -> str:
    """Человекочитаемая метка диапазона, например: 'Аль-Бакара 1-15'."""
    if first["surah"] == last["surah"]:
        return f"{first['surah_name']} {first['ayah']}-{last['ayah']}"
    return (
        f"{first['surah_name']} {first['ayah']} — "
        f"{last['surah_name']} {last['ayah']}"
    )


if __name__ == "__main__":
    build()
