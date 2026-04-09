
import os
from dotenv import load_dotenv

load_dotenv()


def _str(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _int(key: str, default: int) -> int:
    v = os.environ.get(key)
    return int(v) if v not in (None, "") else default


def _float(key: str, default: float) -> float:
    v = os.environ.get(key)
    return float(v) if v not in (None, "") else default


def _bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def _csv_int(key: str) -> list[int]:
    raw = os.environ.get(key, "")
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


# ── Telegram ──────────────────────────────────────────────
TELEGRAM_TOKEN = _str("TELEGRAM_TOKEN")
ALLOWED_USERS: list[int] = _csv_int("ALLOWED_USERS")
ADMIN_USERS: list[int] = _csv_int("ADMIN_USERS")
TRIGGER_WORD = _str("TRIGGER_WORD")

# ── LLM ───────────────────────────────────────────────────
LLM_BASE_URL = _str("LLM_BASE_URL")
LLM_API_KEY = _str("LLM_API_KEY")
MODEL = _str("MODEL", "openai/gpt-4o-mini")
MAX_TOKENS = _int("MAX_TOKENS", 1024)
STREAM_REPLIES = _bool("STREAM_REPLIES", True)

# ── RAG ───────────────────────────────────────────────────
CHROMA_DIR = _str("CHROMA_DIR", "./chroma_db")
CHARACTERS_DIR = _str("CHARACTERS_DIR", "./characters")
DEFAULT_CHARACTER = _str("DEFAULT_CHARACTER", "default")
EMBEDDING_MODEL = _str("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K = _int("TOP_K", 5)
RELEVANCE_THRESHOLD = _float("RELEVANCE_THRESHOLD", 0.8)

# ── Чанкинг ───────────────────────────────────────────────
CHUNK_SIZE = _int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 100)

# ── История ───────────────────────────────────────────────
MAX_HISTORY = _int("MAX_HISTORY", 20)
HISTORY_DB = _str("HISTORY_DB", "./data/history.sqlite")

# ── Анти-флуд ─────────────────────────────────────────────
MIN_INTERVAL_SEC = _float("MIN_INTERVAL_SEC", 1.5)
MAX_INPUT_CHARS = _int("MAX_INPUT_CHARS", 2000)
