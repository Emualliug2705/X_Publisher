import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SERVER_API_KEY = os.getenv("SERVER_API_KEY", "").strip()

X_API_KEY = os.getenv("X_API_KEY", "").strip()
X_API_SECRET = os.getenv("X_API_SECRET", "").strip()
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "").strip()
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()
X_OAUTH2_ACCESS_TOKEN = os.getenv("X_OAUTH2_ACCESS_TOKEN", "").strip()

MAX_TEXT_LENGTH = 280
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "10"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
USAGE_FILE = DATA_DIR / "usage.json"
LOG_FILE = DATA_DIR / "published.jsonl"


def has_oauth1() -> bool:
    return all((X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET))


def has_oauth2() -> bool:
    return bool(X_OAUTH2_ACCESS_TOKEN)
