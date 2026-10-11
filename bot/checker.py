"""Проверка аудио: распознаём речь (Whisper) и сравниваем с текстом аята.

ВАЖНО (честно об MVP):
Это не полноценная проверка таджвида. Мы распознаём, какие слова прочитаны,
и сравниваем их со словами аята БЕЗ огласовок. Так бот ловит пропущенные,
лишние и перепутанные слова — то есть грубые ошибки заучивания.
Тонкости произношения (махрадж, протяжённость) так не проверить — для этого
нужны специализированные модели. Это осознанный компромисс ради работающего MVP.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .config import OPENAI_API_KEY, WHISPER_MODEL

# --- Нормализация арабского текста -----------------------------------------

# Огласовки (харакат), танвин, надстрочные знаки, тату (протяжка).
_DIACRITICS = re.compile(
    "["
    "ؐ-ؚ"
    "ً-ٟ"
    "ٰ"
    "ۖ-ۜ"
    "۟-ۨ"
    "۪-ۭ"
    "ـ"  # tatweel
    "]"
)
# Всё, кроме арабских букв и пробелов.
_NON_LETTERS = re.compile(r"[^ء-ي\s]")


def normalize_arabic(text: str) -> str:
    text = _DIACRITICS.sub("", text)
    text = _NON_LETTERS.sub(" ", text)
    # Унифицируем варианты алифа/хамзы/я/та-марбуты, чтобы сравнение было мягче.
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return normalize_arabic(text).split()


# --- Результат проверки ------------------------------------------------------


@dataclass
class CheckResult:
    accuracy: float            # 0..1
    transcript: str            # что распознал Whisper
    diff_lines: list[str]      # пословный разбор для показа пользователю


def compare(expected: str, actual: str) -> CheckResult:
    exp_tokens = tokenize(expected)
    act_tokens = tokenize(actual)

    matcher = difflib.SequenceMatcher(a=exp_tokens, b=act_tokens, autojunk=False)
    ratio = matcher.ratio()

    diff: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        exp_part = " ".join(exp_tokens[i1:i2])
        act_part = " ".join(act_tokens[j1:j2])
        if tag == "replace":
            diff.append(f"✏️ ожидалось «{exp_part}», услышано «{act_part}»")
        elif tag == "delete":
            diff.append(f"➖ пропущено: «{exp_part}»")
        elif tag == "insert":
            diff.append(f"➕ лишнее: «{act_part}»")

    return CheckResult(accuracy=ratio, transcript=actual, diff_lines=diff)


# --- Распознавание речи ------------------------------------------------------


def transcription_available() -> bool:
    return bool(OPENAI_API_KEY)


def transcribe(audio_path: str) -> str:
    """Распознаёт арабскую речь из файла и возвращает текст."""
    if not OPENAI_API_KEY:
        raise RuntimeError("Не задан OPENAI_API_KEY — распознавание недоступно.")
    from openai import OpenAI  # ленивый импорт: нужен только когда включено аудио

    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language="ar",
        )
    return result.text


def check_recitation(audio_path: str, expected_text: str) -> CheckResult:
    actual = transcribe(audio_path)
    return compare(expected_text, actual)
