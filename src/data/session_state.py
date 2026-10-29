"""세션 시작 시 상태 대조 (KIK-738 후속).

목적
----
AI 가 PF / 현금 / 보유 / 대기 중인 거래에 대해 무언가 말하기 전에 반드시
디스크 상태(portfolio.csv / cash_balance.json / 최근 노트 / 최근 거래 JSON)를
읽어야 한다. 2026-04-29 아침 인사 버그는 AI 가 기억에 의존해 오래된 계획을
그대로 말한 회귀였다.

패턴: `src/data/preflight.py` 와 동일 — 구조화된 dict 를 반환하는 얇은 순수 함수.
SKILL.md 는 호출 지점(`reconcile_session_state()`)만 담고 구현은 담지 않는다.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_iso_date(value: object) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value:
        return None
    s = value.strip().split("T", 1)[0]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _load_portfolio(base_dir: Path) -> list[dict]:
    """`<base_dir>/data/portfolio.csv` 를 직접 파싱한다 (base_dir 존중)."""
    import csv

    path = base_dir / "data" / "portfolio.csv"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _load_cash_balance(base_dir: Path) -> Optional[dict]:
    path = base_dir / "data" / "cash_balance.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_recent_notes(base_dir: Path, window_days: int) -> list[dict]:
    """`date` 가 오늘로부터 `window_days` 이내인 노트를 반환한다."""
    notes_dir = base_dir / "data" / "notes"
    if not notes_dir.exists():
        return []
    cutoff = _today() - timedelta(days=window_days)
    recent: list[dict] = []
    for fp in sorted(notes_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        notes = data if isinstance(data, list) else [data]
        for n in notes:
            if not isinstance(n, dict):
                continue
            d = _parse_iso_date(n.get("date"))
            if d is not None and d >= cutoff:
                recent.append(n)
    # 최신순
    recent.sort(key=lambda n: n.get("date", ""), reverse=True)
    return recent


def _load_recent_trades(base_dir: Path, window_days: int) -> list[str]:
    """`date`(또는 구 형식 `trade_date`)가 window_days 이내인 거래 JSON 파일명을 반환한다.

    KIK-742: save_trade.py 는 `"date"` 키로 저장하지만 과거에는 `trade_date` 도
    사용됐다. 둘 다 폴백으로 읽는다.
    """
    trade_dir = base_dir / "data" / "history" / "trade"
    if not trade_dir.exists():
        return []
    cutoff = _today() - timedelta(days=window_days)
    recent: list[str] = []
    for fp in sorted(trade_dir.glob("*.json"), reverse=True):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # KIK-742: date 가 정식, trade_date 는 구 형식 폴백
        d = _parse_iso_date(rec.get("date") or rec.get("trade_date"))
        if d is not None and d >= cutoff:
            recent.append(fp.name)
    return recent


def reconcile_session_state(
    notes_window_days: int = 7,
    trade_window_days: int = 7,
    cash_stale_days: int = 3,
    base_dir: str = ".",
) -> dict[str, Any]:
    """PF / 현금 / 보유에 대해 말하기 전에 필요한 디스크 상태를 모두 읽는다.

    공개 파사드와 SKILL.md 훅은 tools/session_state.py 참조.
    """
    root = Path(base_dir).resolve()
    portfolio = _load_portfolio(root)
    cash = _load_cash_balance(root)
    recent_notes = _load_recent_notes(root, notes_window_days)
    recent_trades = _load_recent_trades(root, trade_window_days)

    warnings: list[str] = []
    cash_stale = False
    cash_missing = cash is None
    if cash_missing:
        warnings.append("cash_balance.json 을 찾을 수 없습니다")
    else:
        cash_date = _parse_iso_date(cash.get("date"))
        if cash_date is None:
            warnings.append("cash_balance.json 의 date 를 해석할 수 없습니다")
            # 날짜를 읽을 수 없으면 보수적으로 stale 취급
            cash_stale = True
        else:
            age_days = (_today() - cash_date).days
            if age_days > cash_stale_days:
                cash_stale = True
                warnings.append(
                    f"cash_balance.json 은 {cash['date']} 시점 "
                    f"({age_days}일 전) — 최근 거래와 어긋날 가능성"
                )

    if not recent_notes:
        warnings.append(
            f"최근 {notes_window_days}일간 새 note 없음 — "
            "지난 세션 이후 판단 기록이 없을 가능성"
        )

    return {
        "portfolio": portfolio,
        "cash_balance": cash,
        "cash_missing": cash_missing,
        "cash_stale": cash_stale,
        "recent_notes": recent_notes,
        "recent_trades": recent_trades,
        "warnings": warnings,
        "checked_at": _today().isoformat(),
    }


__all__ = ["reconcile_session_state"]
