"""한국 종목 TTM 밸류에이션 계산 (yfinance 분기 재무제표 기반).

Yahoo Finance 는 한국 종목(.KS/.KQ)의 ``trailingPE`` / ``priceToBook`` /
``trailingEps`` / ``bookValue`` 를 제공하지 않는다(2026-10 실측, 코스피·코스닥
전 종목). 대신 분기 손익계산서·재무상태표와 발행주식수는 제공하므로,
최근 4분기(TTM) EPS 와 최근 분기 BPS 를 직접 계산해 PER/PBR 공백을 메운다.

계산 규칙
- EPS: 분기 ``Basic EPS`` 행이 4분기 연속으로 있으면 그 합(우선). 없으면
  4분기 순이익 합 / 발행주식수
- BPS: 최근 분기 자본 / 발행주식수
- PER = 현재가 / EPS (EPS ≤ 0 이면 None), PBR = 현재가 / BPS (BPS ≤ 0 이면 None)
- 분기 컬럼은 최신순으로 정렬하고, 4분기가 약 9개월 간격으로 연속할 때만 TTM 으로 인정
  (한국 기업은 Q4 를 따로 공시하지 않아 Yahoo 분기 데이터에 빈 분기가 생길 수 있다)
- 우선주(종목코드 끝자리 ≠ 0)는 회사 전체 재무제표를 우선주 주식수로 나누게 되어
  왜곡되므로 계산하지 않는다 (pykrx 공급자가 KRX 값을 준다)
- 재무제표 통화(``financialCurrency``)가 시세 통화와 다르면 계산하지 않는다
- 결과는 종목별 24시간 파일 캐시(``{symbol}_valuation.json``)에 저장한다
"""

from typing import Any

import pandas as pd
import yfinance as yf

from src.data.ticker_utils import is_preferred_kr
from src.data.yahoo_client._cache import (
    _read_suffixed_cache,
    _write_suffixed_cache,
)
from src.data.yahoo_client._normalize import _safe_get

SOURCE_NAME = "yfinance-ttm"
VALUATION_CACHE_SUFFIX = "_valuation"

# 분기 손익계산서의 주당순이익 행 후보 (있으면 순이익/주식수보다 우선)
BASIC_EPS_ROWS = ("Basic EPS",)
# 분기 손익계산서의 순이익 행 후보 (우선순위 순)
NET_INCOME_ROWS = (
    "Net Income Common Stockholders",
    "Net Income",
    "Net Income From Continuing Operation Net Minority Interest",
)
# 분기 재무상태표의 자본 행 후보 (우선순위 순)
EQUITY_ROWS = (
    "Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
)
TTM_QUARTERS = 4
# 최신 분기 말 ~ 4번째 분기 말 간격 허용 범위 (정상은 약 273일)
TTM_SPAN_DAYS = (240, 310)


def _sorted_desc(df: Any) -> pd.DataFrame | None:
    """분기 컬럼을 최신순으로 정렬한 DataFrame. 비어 있거나 DataFrame 이 아니면 None."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if not isinstance(df.columns, pd.DatetimeIndex):
        return df  # 날짜 컬럼이 아니면 순서를 신뢰한다
    return df.reindex(sorted(df.columns, reverse=True), axis=1)


def _row_values(
    df: Any, row_names: tuple[str, ...], max_periods: int, require_full: bool = False,
) -> list[float]:
    """후보 행 중 조건을 만족하는 첫 행의 최신→과거 값을 돌려준다.

    NaN 을 만나면 그 앞까지만 쓴다(연속 구간). ``require_full`` 이면
    ``max_periods`` 개가 모두 있는 행만 채택하고, 아니면 다음 후보 행을 본다.
    """
    frame = _sorted_desc(df)
    if frame is None:
        return []
    for name in row_names:
        if name not in frame.index:
            continue
        values: list[float] = []
        row = frame.loc[name]
        for i in range(min(len(row), max_periods)):
            val = row.iloc[i]
            if pd.isna(val):
                break
            values.append(float(val))
        if values and (not require_full or len(values) == max_periods):
            return values
    return []


def _quarters_contiguous(df: Any, n: int = TTM_QUARTERS) -> bool:
    """최신 n개 분기 말 날짜가 약 (n-1)*91일 간격으로 이어지는지 확인한다."""
    frame = _sorted_desc(df)
    if frame is None or len(frame.columns) < n:
        return False
    try:
        newest = pd.Timestamp(frame.columns[0])
        oldest = pd.Timestamp(frame.columns[n - 1])
    except (TypeError, ValueError):
        return False
    span = (newest - oldest).days
    return TTM_SPAN_DAYS[0] <= span <= TTM_SPAN_DAYS[1]


def _latest_period(df: Any) -> str | None:
    """DataFrame 의 최신 분기 말을 ISO 날짜 문자열로 돌려준다."""
    frame = _sorted_desc(df)
    if frame is None:
        return None
    try:
        return pd.Timestamp(frame.columns[0]).date().isoformat()
    except (TypeError, ValueError):
        return None


def _positive_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """denominator 가 양수일 때만 numerator/denominator 를 돌려준다."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _ttm_eps(quarterly_income: Any, shares: float) -> float | None:
    """Basic EPS 4분기 합 → 없으면 순이익 4분기 합 / 주식수. 분기가 불연속이면 None."""
    if not _quarters_contiguous(quarterly_income):
        return None
    basic = _row_values(quarterly_income, BASIC_EPS_ROWS, TTM_QUARTERS, require_full=True)
    if basic:
        return round(sum(basic), 4)
    net_incomes = _row_values(quarterly_income, NET_INCOME_ROWS, TTM_QUARTERS, require_full=True)
    if net_incomes:
        return round(sum(net_incomes) / shares, 4)
    return None


def _strip_cache_meta(data: dict) -> dict:
    return {k: v for k, v in data.items() if k != "_cached_at"}


def compute_ttm_valuation(symbol: str, ticker: Any = None) -> dict | None:
    """분기 재무제표로 TTM EPS/BPS → PER/PBR 을 계산한다.

    Parameters
    ----------
    symbol : str
        yfinance 심볼 (예: 005930.KS)
    ticker : Any, optional
        이미 만들어 둔 ``yf.Ticker`` (중복 조회 방지·테스트 주입). 생략하면 새로 만든다.

    Returns
    -------
    dict | None
        {symbol, per, pbr, eps, bps, price, shares_outstanding, as_of, source}.
        우선주·통화 불일치·발행주식수/가격 누락·네 지표 모두 None 이면 None.
    """
    if is_preferred_kr(symbol):
        return None

    cached = _read_suffixed_cache(symbol, VALUATION_CACHE_SUFFIX)
    if cached is not None:
        return _strip_cache_meta(cached)

    try:
        t = ticker if ticker is not None else yf.Ticker(symbol)
        info = t.info or {}
        shares = _safe_get(info, "sharesOutstanding")
        price = _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice")
        if not shares or not price or shares <= 0:
            return None
        fin_ccy = info.get("financialCurrency")
        quote_ccy = info.get("currency")
        if fin_ccy and quote_ccy and fin_ccy != quote_ccy:
            return None

        quarterly_income = t.quarterly_financials
        quarterly_balance = t.quarterly_balance_sheet

        eps = _ttm_eps(quarterly_income, float(shares))
        equities = _row_values(quarterly_balance, EQUITY_ROWS, 1)
        bps = round(equities[0] / shares, 4) if equities else None

        result = {
            "symbol": symbol,
            "per": _positive_ratio(price, eps),
            "pbr": _positive_ratio(price, bps),
            "eps": eps,
            "bps": bps,
            "price": float(price),
            "shares_outstanding": float(shares),
            "as_of": _latest_period(quarterly_income) or _latest_period(quarterly_balance),
            "source": SOURCE_NAME,
        }
        if all(result[k] is None for k in ("per", "pbr", "eps", "bps")):
            return None

        _write_suffixed_cache(symbol, VALUATION_CACHE_SUFFIX, dict(result))
        return result
    except Exception as e:
        print(f"[yahoo_client] {symbol} TTM 밸류에이션 계산 실패: {e}")
        return None
