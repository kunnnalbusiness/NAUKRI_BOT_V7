"""
Remembers answers to screening questions you've typed in yourself before,
keyed by a normalized version of the question text, so you're never asked
the same question twice across runs.

Stored dynamically in data/cache/learned_answers.json (or project root).
"""

import json
import re

from common.paths import get_learned_answers_path


def _normalize(question: str) -> str:
    q = question.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(
        r"[^\w\s]", "", q
    )  # drop punctuation so minor phrasing differences still match
    return q


def _load() -> dict:
    store_path = get_learned_answers_path()
    if not store_path.exists():
        return {}
    try:
        return json.loads(store_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    store_path = get_learned_answers_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_answer(question: str) -> str | None:
    data = _load()
    return data.get(_normalize(question))


def save_answer(question: str, answer: str):
    data = _load()
    data[_normalize(question)] = answer
    _save(data)
