"""포트폴리오 I/O: CSV 읽기/쓰기와 포지션 조작 (KIK-578 분리).

portfolio_manager.py 에서 추출. CSV 기반 포트폴리오 영속화와
포지션 추적·손익 계산을 제공한다.
"""

import csv
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from src.data.ticker_utils import (
    SUFFIX_TO_CURRENCY as _SUFFIX_TO_CURRENCY,
    infer_currency as _infer_currency,
)

# 기본 통화 (기준 통화)
BASE_CURRENCY = "KRW"


def _resolve_currency(symbol: str, currency: Optional[str]) -> str:
    """cost_currency 가 비어 있으면 심볼 접미사로 통화를 추론한다.

    미국 종목(접미사 없음)을 원화로 기록하면 손익이 환율 배수만큼 틀어지므로
    기본값을 BASE_CURRENCY 로 고정하지 않는다.
    """
    value = (currency or "").strip()
    if value:
        return value
    return _infer_currency(symbol) if symbol else BASE_CURRENCY

# CSV 경로 (기본값)
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "data",
    "portfolio.csv",
)

# CSV 열 정의
CSV_COLUMNS = [
    "symbol",
    "shares",
    "cost_price",
    "cost_currency",
    "purchase_date",
    "memo",
    "next_earnings",  # KIK-683: 다음 실적 발표일 (YYYY-MM-DD). ETF 는 공란
    "div_yield",      # KIK-694: 배당수익률 (%)
    "buyback_yield",  # KIK-694: 자사주매입수익률 (%)
    "total_return",   # KIK-694: 총주주환원율 (%) = div_yield + buyback_yield
    "beta",           # KIK-694: 베타
    "role",           # KIK-694: PF 내 역할 (장기인컴/성장/헤지 등)
]


def _fmt_float(value) -> str:
    """CSV 용 float 포맷. None → 빈 문자열."""
    if value is None:
        return ""
    return str(value)


def _safe_float(value: str) -> float | None:
    """CSV 문자열을 float 로 파싱. 비어 있거나 잘못되면 None."""
    if not value or not str(value).strip():
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def load_portfolio(csv_path: str = DEFAULT_CSV_PATH) -> list[dict]:
    """CSV 에서 포트폴리오를 읽는다.

    Returns
    -------
    list[dict]
        각 행이 dict: {symbol, shares, cost_price, cost_currency, purchase_date, memo, ...}
        shares 는 int, cost_price 는 float 로 변환됨.
        파일이 없으면 빈 리스트를 반환한다.
    """
    csv_path = os.path.normpath(csv_path)
    if not os.path.exists(csv_path):
        return []

    portfolio: list[dict] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # KIK-744: 행 단위 try/except 로 숫자 손상 시 전체가 실패하지 않게 한다
            try:
                shares_int = int(float(row.get("shares", 0)))
                cost_price_f = float(row.get("cost_price", 0.0))
            except (TypeError, ValueError) as e:
                logger.warning(
                    "손상된 포트폴리오 행 건너뜀 symbol=%r: %s",
                    row.get("symbol", ""), e,
                )
                continue
            position = {
                "symbol": row.get("symbol", "").strip(),
                "shares": shares_int,
                "cost_price": cost_price_f,
                "cost_currency": _resolve_currency(
                    row.get("symbol", ""), row.get("cost_currency"),
                ),
                "purchase_date": row.get("purchase_date", "").strip(),
                "memo": row.get("memo", "").strip(),
                "next_earnings": row.get("next_earnings", "").strip(),
                "div_yield": _safe_float(row.get("div_yield", "")),
                "buyback_yield": _safe_float(row.get("buyback_yield", "")),
                "total_return": _safe_float(row.get("total_return", "")),
                "beta": _safe_float(row.get("beta", "")),
                "role": row.get("role", "").strip(),
            }
            if position["symbol"] and position["shares"] > 0:
                portfolio.append(position)

    return portfolio


DEFAULT_CASH_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "data",
    "cash_balance.json",
)


def load_cash_balance(cash_path: str | None = None) -> dict:
    """KIK-734: cash_balance.json 을 읽는다 (PF 총자산 계산에 필수).

    KIK-735: cash_path=None 이면 `DEFAULT_CASH_PATH` 를 지연 참조한다
    (테스트의 monkeypatch 가 반영되도록).

    Returns
    -------
    dict
        {"total_krw": float, "breakdown": {"KRW": {...}, "USD": {...}}, "date": str, ...}
        파일이 없으면 빈 dict 를 반환한다.
    """
    import json
    if cash_path is None:
        cash_path = DEFAULT_CASH_PATH
    cash_path = os.path.normpath(cash_path)
    if not os.path.exists(cash_path):
        return {}
    with open(cash_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_total_assets(
    csv_path: str | None = None,
    cash_path: str | None = None,
) -> dict:
    """KIK-734: PF 총자산(주식 + 현금)을 가져오는 SSoT 함수.

    HC / Risk Assessor 가 현금 참조를 빠뜨리지 않도록 주식과 현금을
    한 번에 가져온다. Cash% 비율을 정확히 계산하려면 반드시 이 함수를 쓸 것.

    Returns
    -------
    dict
        {
            "positions": list[dict],   # load_portfolio() 결과
            "cash": dict,              # load_cash_balance() 결과
            "cash_krw": float,         # 현금 합계 (KRW 환산)
            "has_cash": bool,          # cash_balance.json 을 읽었는지
        }
    """
    # KIK-735: monkeypatch 가 반영되도록 기본값을 동적으로 조회
    if csv_path is None:
        csv_path = DEFAULT_CSV_PATH
    if cash_path is None:
        cash_path = DEFAULT_CASH_PATH
    positions = load_portfolio(csv_path)
    cash = load_cash_balance(cash_path)
    # KIK-734 리뷰: has_cash 는 total_krw 를 읽었을 때만 True.
    # cash_balance.json 은 있지만 total_krw 가 빠진 경우를 구분한다.
    has_total_krw = isinstance(cash, dict) and "total_krw" in cash
    cash_krw = float(cash.get("total_krw") or 0) if has_total_krw else 0.0
    return {
        "positions": positions,
        "cash": cash or {},
        "cash_krw": cash_krw,
        "has_cash": has_total_krw,
    }


def save_portfolio(
    portfolio: list[dict], csv_path: str = DEFAULT_CSV_PATH
) -> None:
    """포트폴리오를 CSV 로 저장한다.

    디렉터리가 없으면 자동 생성한다.
    """
    csv_path = os.path.normpath(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for pos in portfolio:
            writer.writerow(
                {
                    "symbol": pos.get("symbol", ""),
                    "shares": pos.get("shares", 0),
                    "cost_price": pos.get("cost_price", 0.0),
                    "cost_currency": _resolve_currency(
                        pos.get("symbol", ""), pos.get("cost_currency"),
                    ),
                    "purchase_date": pos.get("purchase_date", ""),
                    "memo": pos.get("memo", ""),
                    "next_earnings": pos.get("next_earnings", ""),
                    "div_yield": _fmt_float(pos.get("div_yield")),
                    "buyback_yield": _fmt_float(pos.get("buyback_yield")),
                    "total_return": _fmt_float(pos.get("total_return")),
                    "beta": _fmt_float(pos.get("beta")),
                    "role": pos.get("role", ""),
                }
            )


# ---------------------------------------------------------------------------
# 포지션 조작
# ---------------------------------------------------------------------------


def add_position(
    csv_path: str,
    symbol: str,
    shares: int,
    cost_price: float,
    cost_currency: Optional[str] = None,
    purchase_date: Optional[str] = None,
    memo: str = "",
) -> dict:
    """신규 포지션 추가 또는 기존 포지션 추가 매수.

    기존 종목이 있으면:
    - 주식 수를 더하고
    - 평균 매수단가를 재계산: new_avg = (old_shares * old_price + new_shares * new_price) / total_shares
    - purchase_date 는 최신 날짜로 갱신

    Returns
    -------
    dict
        갱신 후 포지션 dict

    Raises
    ------
    ValueError
        shares <= 0 또는 cost_price <= 0 인 경우 (KIK-742).
    """
    # KIK-742: 입력 검증 (음수·0 을 거부해 PF 파손을 막는다)
    if not isinstance(shares, (int, float)) or shares <= 0:
        raise ValueError(f"shares must be > 0, got {shares!r}")
    if not isinstance(cost_price, (int, float)) or cost_price <= 0:
        raise ValueError(f"cost_price must be > 0, got {cost_price!r}")

    if purchase_date is None:
        purchase_date = datetime.now().strftime("%Y-%m-%d")

    # 통화를 생략하면 심볼 접미사로 추론한다 (.KS/.KQ → KRW, 접미사 없음 → USD)
    cost_currency = _resolve_currency(symbol, cost_currency)

    portfolio = load_portfolio(csv_path)

    # 같은 종목의 기존 포지션 검색
    existing = None
    for pos in portfolio:
        if pos["symbol"].upper() == symbol.upper():
            existing = pos
            break

    if existing is not None:
        # KIK-744: 통화 혼재 거부 (평균 매수단가가 깨지므로)
        existing_currency = _resolve_currency(symbol, existing.get("cost_currency")).upper()
        new_currency = cost_currency.upper()
        if existing_currency != new_currency:
            raise ValueError(
                f"cost_currency mismatch for {symbol}: existing={existing_currency!r}, "
                f"new={new_currency!r}. Cannot mix currencies in average cost basis."
            )
        # 기존 포지션 추가 매수 → 평균 매수단가 재계산
        old_shares = existing["shares"]
        old_price = existing["cost_price"]
        total_shares = old_shares + shares
        if total_shares > 0:
            new_avg = (old_shares * old_price + shares * cost_price) / total_shares
        else:
            new_avg = cost_price

        existing["shares"] = total_shares
        existing["cost_price"] = round(new_avg, 4)
        existing["purchase_date"] = purchase_date
        if memo:
            existing["memo"] = memo
        result = dict(existing)
    else:
        # 신규 포지션
        new_pos = {
            "symbol": symbol.upper() if "." not in symbol else symbol,
            "shares": shares,
            "cost_price": cost_price,
            "cost_currency": cost_currency,
            "purchase_date": purchase_date,
            "memo": memo,
            "next_earnings": "",
            "div_yield": None,
            "buyback_yield": None,
            "total_return": None,
            "beta": None,
            "role": "",
        }
        portfolio.append(new_pos)
        result = dict(new_pos)

    save_portfolio(portfolio, csv_path)
    return result


def sell_position(
    csv_path: str,
    symbol: str,
    shares: int,
    sell_price: Optional[float] = None,
    sell_date: Optional[str] = None,
) -> dict:
    """매도. shares 만큼 차감하고 0 이하가 되면 행을 삭제한다.

    Parameters
    ----------
    sell_price : float, optional
        매도 단가. 지정 시 realized_pnl / pnl_rate 를 계산한다.
    sell_date : str, optional
        매도일 (YYYY-MM-DD). 지정 시 hold_days 를 계산한다.

    Returns
    -------
    dict
        갱신 후 포지션 dict (삭제된 경우 shares=0 인 dict).
        KIK-441: sold_shares / sell_price / realized_pnl / pnl_rate / hold_days 추가.

    Raises
    ------
    ValueError
        종목을 찾을 수 없거나, 보유 수량을 초과해 매도하거나,
        shares/sell_price 가 <= 0 인 경우 (KIK-742).
    """
    # KIK-742: 입력 검증 (음수·0 을 거부해 PF 파손을 막는다)
    if not isinstance(shares, (int, float)) or shares <= 0:
        raise ValueError(f"shares must be > 0, got {shares!r}")
    if sell_price is not None and (
        not isinstance(sell_price, (int, float)) or sell_price <= 0
    ):
        raise ValueError(f"sell_price must be > 0 if provided, got {sell_price!r}")

    portfolio = load_portfolio(csv_path)

    target_idx = None
    for i, pos in enumerate(portfolio):
        if pos["symbol"].upper() == symbol.upper():
            target_idx = i
            break

    if target_idx is None:
        raise ValueError(f"종목 {symbol}은(는) 포트폴리오에 없습니다.")

    target = portfolio[target_idx]

    if shares > target["shares"]:
        raise ValueError(
            f"종목 {symbol}의 보유 수량({target['shares']})을 초과하는 "
            f"매도 수량({shares})이 지정되었습니다."
        )

    remaining = target["shares"] - shares

    if remaining <= 0:
        # 전량 매도 → 행 삭제
        result = dict(target)
        result["shares"] = 0
        portfolio.pop(target_idx)
    else:
        target["shares"] = remaining
        result = dict(target)

    save_portfolio(portfolio, csv_path)

    # KIK-441: 손익 필드 추가
    result["sold_shares"] = shares
    result["sell_price"] = sell_price

    cost_price = target.get("cost_price")
    if sell_price is not None and cost_price is not None and cost_price != 0:
        result["realized_pnl"] = (sell_price - cost_price) * shares
        result["pnl_rate"] = (sell_price - cost_price) / cost_price
    else:
        result["realized_pnl"] = None
        result["pnl_rate"] = None

    purchase_date = target.get("purchase_date", "")
    if sell_date and purchase_date:
        try:
            from datetime import date as _date
            d1 = _date.fromisoformat(purchase_date)
            d2 = _date.fromisoformat(sell_date)
            result["hold_days"] = (d2 - d1).days
        except (ValueError, TypeError):
            result["hold_days"] = None
    else:
        result["hold_days"] = None

    return result


def update_next_earnings(
    csv_path: str,
    symbol: str,
    next_earnings: str,
) -> bool:
    """특정 종목의 next_earnings 를 갱신한다 (KIK-683).

    Parameters
    ----------
    csv_path : str
        포트폴리오 CSV 경로
    symbol : str
        티커 심볼
    next_earnings : str
        실적 발표일 (YYYY-MM-DD). 빈 문자열이면 지운다

    Returns
    -------
    bool
        갱신 성공이면 True, 종목을 찾지 못하면 False
    """
    portfolio = load_portfolio(csv_path)
    found = False
    for pos in portfolio:
        if pos["symbol"].upper() == symbol.upper():
            pos["next_earnings"] = next_earnings
            found = True
            break
    if found:
        save_portfolio(portfolio, csv_path)
    return found


def update_return_profile(
    csv_path: str,
    symbol: str,
    div_yield: float | None = None,
    buyback_yield: float | None = None,
    total_return: float | None = None,
    beta: float | None = None,
    role: str | None = None,
) -> bool:
    """특정 종목의 환원율·베타·역할을 갱신한다 (KIK-694).

    None 인 필드는 갱신하지 않는다 (기존 값 유지).

    Returns
    -------
    bool
        갱신 성공이면 True, 종목을 찾지 못하면 False
    """
    portfolio = load_portfolio(csv_path)
    found = False
    for pos in portfolio:
        if pos["symbol"].upper() == symbol.upper():
            if div_yield is not None:
                pos["div_yield"] = div_yield
            if buyback_yield is not None:
                pos["buyback_yield"] = buyback_yield
            if total_return is not None:
                pos["total_return"] = total_return
            if beta is not None:
                pos["beta"] = beta
            if role is not None:
                pos["role"] = role
            found = True
            break
    if found:
        save_portfolio(portfolio, csv_path)
    return found


def get_performance_review(
    year: Optional[int] = None,
    symbol: Optional[str] = None,
    base_dir: str = "data/history",
) -> dict:
    """매매 성과 리뷰 집계 (KIK-441).

    data/history/trade/*.json 에서 trade_type="sell" 이고
    realized_pnl 이 있는 레코드를 집계해 통계를 반환한다.

    Parameters
    ----------
    year : int, optional
        특정 연도로 필터 (예: 2026). None 이면 전체 기간.
    symbol : str, optional
        특정 심볼로 필터. None 이면 전 종목.
    base_dir : str
        history 루트 디렉터리.

    Returns
    -------
    dict
        {
            "trades": [...],  # 필터된 sell 레코드 목록
            "stats": {
                "total": int,
                "wins": int,
                "win_rate": float | None,
                "avg_return": float | None,   # pnl_rate 평균
                "avg_hold_days": float | None,
                "total_pnl": float | None,
            }
        }
    """
    from src.data.history import load_history

    all_trades = load_history("trade", base_dir=base_dir)

    # sell 이면서 realized_pnl 이 있는 것만
    sells = [
        t for t in all_trades
        if t.get("trade_type") == "sell" and t.get("realized_pnl") is not None
    ]

    # year 필터
    if year is not None:
        sells = [t for t in sells if str(t.get("date", "")).startswith(str(year))]

    # symbol 필터
    if symbol is not None:
        sym_upper = symbol.upper()
        sells = [t for t in sells if t.get("symbol", "").upper() == sym_upper]

    # 통계 계산
    total = len(sells)
    if total == 0:
        return {
            "trades": [],
            "stats": {
                "total": 0,
                "wins": 0,
                "win_rate": None,
                "avg_return": None,
                "avg_hold_days": None,
                "total_pnl": None,
            },
        }

    wins = sum(1 for t in sells if (t.get("realized_pnl") or 0) > 0)
    win_rate = wins / total

    pnl_rates_stored = [t["pnl_rate"] for t in sells if t.get("pnl_rate") is not None]
    avg_return = sum(pnl_rates_stored) / len(pnl_rates_stored) if pnl_rates_stored else None

    hold_days_list = [t["hold_days"] for t in sells if t.get("hold_days") is not None]
    avg_hold_days = sum(hold_days_list) / len(hold_days_list) if hold_days_list else None

    total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in sells)

    return {
        "trades": sells,
        "stats": {
            "total": total,
            "wins": wins,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "avg_hold_days": avg_hold_days,
            "total_pnl": total_pnl,
        },
    }
