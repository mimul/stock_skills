"""현금 잔고 도구 — 잔고 읽기/쓰기 파사드 (KIK-742 계층 형식 SSoT).

tools/ 계층은 저장·조회만 담당한다. 판단 로직은 포함하지 않는다.
data/cash_balance.json 을 직접 읽고 쓴다.

# 현금 잔고 스키마 (SSoT)

계층 형식(실데이터 기준, KIK-742 에서 통일):

```json
{
  "date": "YYYY-MM-DD",
  "timestamp": "ISO-8601",
  "total_krw": 10000000,
  "breakdown": {
    "KRW": {"amount": 7200000},
    "USD": {"amount": 2000.0, "krw_equivalent": 2800000, "rate_krw_per_usd": 1400.0}
  },
  "changelog": ["..."]
}
```

`session_state.py` 와 `src/data/portfolio_io.py:load_cash_balance` 도 같은 형식을 기대한다.
"""

import json
import os
from datetime import datetime
from pathlib import Path

_CASH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "cash_balance.json"
)


def load_cash_balance(path: str = _CASH_PATH) -> dict:
    """현금 잔고를 읽는다 (계층 형식, KIK-742).

    Returns
    -------
    dict
        {"date": str, "total_krw": float, "breakdown": {...}, ...}
        파일이 없으면 빈 dict 를 반환한다.
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cash_balance(balances: dict, path: str = _CASH_PATH) -> None:
    """현금 잔고를 저장한다 (계층 형식, KIK-742).

    Parameters
    ----------
    balances : dict
        계층 형식(모듈 docstring 참조).
        date / timestamp 는 자동 부여된다 (기존 date 가 있으면 덮어쓰지 않음).

    Notes
    -----
    구 평면 형식({"KRW": 1234, "USD": 5.6})은 지원하지 않는다.
    기존 JSON 을 편집할 때는 load_cash_balance() 로 읽은 뒤 넘길 것.
    """
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    balances.setdefault("date", now.strftime("%Y-%m-%d"))
    balances["timestamp"] = now.isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2, ensure_ascii=False)


def update_currency(
    currency: str,
    amount: float,
    path: str = _CASH_PATH,
    *,
    krw_equivalent: float | None = None,
    rate_krw_per_usd: float | None = None,
) -> dict:
    """특정 통화의 잔고를 갱신하고 갱신 후 전체 잔고를 반환한다 (계층 형식, KIK-742).

    Parameters
    ----------
    currency : str
        통화 코드 ("KRW", "USD")
    amount : float
        잔고 금액 (해당 통화 단위)
    krw_equivalent : float, optional
        KRW 환산액 (USD 등 외화에서는 사실상 필수)
    rate_krw_per_usd : float, optional
        적용 환율 (외화 기록 시)
    """
    balances = load_cash_balance(path)
    balances.setdefault("breakdown", {})
    entry: dict = {"amount": amount}
    if krw_equivalent is not None:
        entry["krw_equivalent"] = krw_equivalent
    if rate_krw_per_usd is not None:
        entry["rate_krw_per_usd"] = rate_krw_per_usd
    balances["breakdown"][currency.upper()] = entry
    # total_krw 는 호출자 책임 (다통화 합산 로직은 포함하지 않음)
    save_cash_balance(balances, path)
    return balances


__all__ = [
    "load_cash_balance",
    "save_cash_balance",
    "update_currency",
]
