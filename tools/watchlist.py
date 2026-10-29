"""Watchlist Tool — 워치리스트 읽기/쓰기 파사드.

tools/ 층은 저장·조회만 담당한다. 판단 로직은 포함하지 않는다.
data/watchlists/ 의 JSON 파일을 직접 읽고 쓴다.
"""

import json
import os
from pathlib import Path

_WATCHLISTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "watchlists"
)


def _ensure_dir() -> Path:
    d = Path(_WATCHLISTS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_path(list_name: str) -> Path:
    return _ensure_dir() / f"{list_name}.json"


def list_watchlists() -> list[str]:
    """사용 가능한 워치리스트 이름 목록을 반환한다."""
    d = _ensure_dir()
    return [p.stem for p in sorted(d.glob("*.json"))]


def load_watchlist(list_name: str = "default") -> list[str]:
    """워치리스트의 심볼 목록을 읽어 온다."""
    path = _list_path(list_name)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(list_name: str, symbols: list[str]) -> None:
    """워치리스트를 저장한다."""
    path = _list_path(list_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(set(symbols)), f, indent=2, ensure_ascii=False)


def add_to_watchlist(list_name: str, *symbols: str) -> list[str]:
    """워치리스트에 심볼을 추가하고 갱신된 목록을 반환한다."""
    current = load_watchlist(list_name)
    updated = sorted(set(current) | set(symbols))
    save_watchlist(list_name, updated)
    return updated


def remove_from_watchlist(list_name: str, *symbols: str) -> list[str]:
    """워치리스트에서 심볼을 삭제하고 갱신된 목록을 반환한다."""
    current = load_watchlist(list_name)
    updated = sorted(set(current) - set(symbols))
    save_watchlist(list_name, updated)
    return updated


__all__ = [
    "list_watchlists",
    "load_watchlist",
    "save_watchlist",
    "add_to_watchlist",
    "remove_from_watchlist",
]
