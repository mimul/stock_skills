"""Cache helpers for yahoo_client (KIK-449)."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cache"
CACHE_TTL_HOURS = 24


def _cache_path(symbol: str) -> Path:
    """Return the cache file path for a given symbol."""
    safe_name = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe_name}.json"


def _read_cache(symbol: str) -> Optional[dict]:
    """Read cached data if it exists and is still valid."""
    return _read_suffixed_cache(symbol, "")


def _write_cache(symbol: str, data: dict) -> None:
    """Write data to cache with a timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = datetime.now().isoformat()
    path = _cache_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Detail cache helpers
# ---------------------------------------------------------------------------

def _detail_cache_path(symbol: str) -> Path:
    """Return the detail-cache file path for a given symbol."""
    safe_name = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe_name}_detail.json"


def _read_detail_cache(symbol: str) -> Optional[dict]:
    """Read detail-cached data if it exists and is still valid (24h TTL)."""
    return _read_suffixed_cache(symbol, "_detail")


def _write_detail_cache(symbol: str, data: dict) -> None:
    """Write detail data to cache with a timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = datetime.now().isoformat()
    path = _detail_cache_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Suffixed cache helpers (심볼 + 접미사 단위의 보조 캐시, 24h TTL)
# ---------------------------------------------------------------------------

def _suffixed_cache_path(symbol: str, suffix: str) -> Path:
    """``{symbol}{suffix}.json`` 형태의 보조 캐시 경로를 돌려준다."""
    safe_name = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe_name}{suffix}.json"


def _read_suffixed_cache(symbol: str, suffix: str) -> Optional[dict]:
    """보조 캐시를 읽는다. 없거나 24h 가 지났거나 손상되었으면 None."""
    path = _suffixed_cache_path(symbol, suffix)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        cached_at = datetime.fromisoformat(data.get("_cached_at", ""))
        if datetime.now() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return None


def _write_suffixed_cache(symbol: str, suffix: str, data: dict) -> None:
    """보조 캐시에 타임스탬프를 붙여 저장한다."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = datetime.now().isoformat()
    path = _suffixed_cache_path(symbol, suffix)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
