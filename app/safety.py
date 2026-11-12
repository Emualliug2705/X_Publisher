import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import DATA_DIR, LOG_FILE, MAX_POSTS_PER_DAY, TIMEZONE, USAGE_FILE

# Official-style X weights: default 2, Basic Latin / some punctuation 1.
# URLs are counted as a t.co length of 23.
_TCO_LENGTH = 23
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _today() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


def _char_weight(cp: int) -> int:
    if cp <= 4351 or 8192 <= cp <= 8205 or 8208 <= cp <= 8223 or 8242 <= cp <= 8247:
        return 1
    return 2


def weighted_length(text: str) -> int:
    """Approximate X weighted length: emoji/CJK = 2, URLs = 23."""
    if not text:
        return 0
    length = 0
    pos = 0
    for match in _URL_RE.finditer(text):
        for ch in text[pos : match.start()]:
            length += _char_weight(ord(ch))
        length += _TCO_LENGTH
        pos = match.end()
    for ch in text[pos:]:
        length += _char_weight(ord(ch))
    return length


def posts_today() -> int:
    if not USAGE_FILE.exists():
        return 0
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if data.get("date") != _today():
        return 0
    return int(data.get("count", 0))


def check_daily_cap() -> None:
    """Raise ValueError if the daily cap has already been reached."""
    used = posts_today()
    if used >= MAX_POSTS_PER_DAY:
        raise ValueError(
            f"Daily cap reached ({used}/{MAX_POSTS_PER_DAY} posts today, "
            f"timezone {TIMEZONE}). Raise MAX_POSTS_PER_DAY or wait until tomorrow."
        )


def increment_daily_count() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = _today()
    used = posts_today()
    next_count = used + 1
    USAGE_FILE.write_text(
        json.dumps({"date": today, "count": next_count}, indent=2) + "\n",
        encoding="utf-8",
    )
    return next_count


def is_duplicate(text: str, in_reply_to: str | None) -> bool:
    if not LOG_FILE.exists():
        return False
    target_reply = in_reply_to or ""
    try:
        with LOG_FILE.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("text") == text and (rec.get("in_reply_to") or "") == target_reply:
                    return True
    except OSError:
        return False
    return False


def log_publication(entry: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
        **entry,
    }
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
