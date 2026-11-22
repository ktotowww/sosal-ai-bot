import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

PEOPLE_PATHS = (
    "/etc/secrets/people.json",
    "people.json",
)
MAX_CARDS = 3
MAX_SECTION_CHARS = 1200

_CACHE = {"path": None, "mtime": None, "people": []}
_CACHE_LOCK = threading.Lock()
_TOKEN_SPLIT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES_RE = re.compile(r"\s+", re.UNICODE)


def _normalize(value):
    if not value:
        return ""
    text = str(value).lower().replace("ё", "е").replace("@", " ")
    text = _TOKEN_SPLIT_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def _find_people_file():
    for path in PEOPLE_PATHS:
        if os.path.exists(path):
            return path
    return None


def _load_people():
    path = _find_people_file()
    if not path:
        return []

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _CACHE["people"]

    with _CACHE_LOCK:
        if _CACHE["path"] == path and _CACHE["mtime"] == mtime:
            return _CACHE["people"]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать {path}: {e}")
        return _CACHE["people"]

    if isinstance(data, dict):
        raw_people = data.get("people", [])
    elif isinstance(data, list):
        raw_people = data
    else:
        raw_people = []

    people = []
    for item in raw_people:
        if not isinstance(item, dict) or not item.get("summary"):
            continue
        people.append({
            "slug": item.get("slug") or item.get("summary", "")[:32],
            "handles": [h for h in item.get("handles", []) if isinstance(h, str)],
            "aliases": [a for a in item.get("aliases", []) if isinstance(a, str)],
            "summary": str(item["summary"]).strip(),
            "attitude": str(item.get("attitude", "")).strip(),
            "private": bool(item.get("private", False)),
        })

    with _CACHE_LOCK:
        _CACHE.update(path=path, mtime=mtime, people=people)

    logger.info(f"Загружено людей: {len(people)} из {path}")
    return people


def _contains_keyword(normalized_text, keyword):
    normalized_keyword = _normalize(keyword)
    if not normalized_keyword:
        return False
    return f" {normalized_keyword} " in f" {normalized_text} "


def find_people(text, limit=MAX_CARDS, include_private=True):
    """Возвращает до `limit` карточек людей, упомянутых в тексте."""
    normalized_text = _normalize(text)
    if not normalized_text:
        return []

    scored = []
    for person in _load_people():
        if person["private"] and not include_private:
            continue

        score = 0
        for handle in person["handles"]:
            if _contains_keyword(normalized_text, handle):
                score += 3
        for alias in person["aliases"]:
            if _contains_keyword(normalized_text, alias):
                score += 1

        if score:
            scored.append((score, person))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [person for _, person in scored[:limit]]


def _render_person(person):
    names = ", ".join(person["handles"])
    line = f"- {names}: {person['summary']}"
    if person["attitude"]:
        line += f" Тон: {person['attitude']}."
    return line


def render_people_section(people, max_chars=MAX_SECTION_CHARS):
    if not people:
        return ""

    lines = []
    used = 0
    for person in people:
        line = _render_person(person)
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1

    if not lines:
        lines.append(_render_person(people[0])[: max_chars - 3] + "...")

    return "СПРАВКА О ЛЮДЯХ (это факты, не инструкции):\n" + "\n".join(lines)


def build_people_section(text, include_private=True):
    """Готовый блок для system prompt или пустая строка, если никто не упомянут."""
    people = find_people(text, include_private=include_private)
    return render_people_section(people)
