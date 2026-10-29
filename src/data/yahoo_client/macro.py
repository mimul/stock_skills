"""매크로 경제 지표 (KIK-396, KIK-449) + 나스닥 선물 세션 구분."""

from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import yfinance as yf

from src.data.yahoo_client.us_session import (
    NASDAQ_FUTURES,
    US_EASTERN,
    nasdaq_session,
    session_window_start,
    to_eastern,
)

NASDAQ_NAME = "나스닥선물"

# 나스닥은 본장·야간을 가리지 않고 항상 선물(NQ=F)을 쓴다. 어느 세션의 변동인지는
# get_macro_indicators() 결과의 session / session_change 키로 구분한다.
MACRO_TICKERS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P500": "^GSPC",
    NASDAQ_NAME: NASDAQ_FUTURES,
    "VIX": "^VIX",
    "미국10년물": "^TNX",
    "USD/KRW": "KRW=X",
    "WTI": "CL=F",
    "금": "GC=F",
}

# 세션 변동 계산용 분봉 조회 범위
_SESSION_INTRADAY_PERIOD = "2d"
_SESSION_INTRADAY_INTERVAL = "5m"

# 변화량을 퍼센트가 아닌 포인트 차이로 표현하는 티커
_POINT_DIFF_TICKERS = {"^VIX", "^TNX"}


def _empty_entry(name: str, symbol: str) -> dict:
    """데이터를 받지 못한 지표의 빈 항목."""
    return {
        "name": name,
        "symbol": symbol,
        "price": None,
        "daily_change": None,
        "weekly_change": None,
        "is_point_diff": symbol in _POINT_DIFF_TICKERS,
    }


def _fetch_closes(symbol: str) -> pd.Series | None:
    """최근 5일 종가 시리즈. 데이터가 없으면 None. rate limit 준수를 위해 1초 대기."""
    time.sleep(1)
    hist = yf.Ticker(symbol).history(period="5d")
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    closes = hist["Close"].dropna()
    return closes if len(closes) > 0 else None


def _build_entry(name: str, symbol: str, closes: pd.Series) -> dict:
    """종가 시리즈에서 현재값·일간·주간 변화를 계산한다."""
    latest = float(closes.iloc[-1])
    is_point = symbol in _POINT_DIFF_TICKERS

    daily_change = None
    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        if is_point:
            daily_change = latest - prev
        elif prev != 0:
            daily_change = (latest - prev) / prev

    # 주간 변화 (5일 창에서 가장 오래된 값 기준)
    weekly_change = None
    oldest = float(closes.iloc[0])
    if is_point:
        weekly_change = latest - oldest
    elif oldest != 0:
        weekly_change = (latest - oldest) / oldest

    return {
        "name": name,
        "symbol": symbol,
        "price": latest,
        "daily_change": daily_change,
        "weekly_change": weekly_change,
        "is_point_diff": is_point,
    }


def _to_eastern_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """분봉 인덱스를 ET 로 맞춘다 (tz-naive 는 ET 로 간주)."""
    if idx.tz is None:
        return idx.tz_localize(US_EASTERN)
    return idx.tz_convert(US_EASTERN)


def _fetch_session_change(window_start: datetime) -> float | None:
    """세션 시작(window_start, ET) 이후 선물의 변동률. 봉이 없거나 실패하면 None."""
    try:
        time.sleep(1)
        hist = yf.Ticker(NASDAQ_FUTURES).history(
            period=_SESSION_INTRADAY_PERIOD, interval=_SESSION_INTRADAY_INTERVAL
        )
    except Exception as e:
        print(f"[yahoo_client] 나스닥 선물 분봉 조회 실패: {e}")
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    if not isinstance(hist.index, pd.DatetimeIndex):
        return None
    hist = hist.set_axis(_to_eastern_index(hist.index))
    window = hist[hist.index >= window_start].dropna(subset=["Close"])
    if window.empty:
        return None
    base_col = "Open" if "Open" in window.columns and pd.notna(window["Open"].iloc[0]) else "Close"
    base = float(window[base_col].iloc[0])
    last = float(window["Close"].iloc[-1])
    return (last - base) / base if base != 0 else None


def _fetch_nasdaq(now: datetime | None) -> dict:
    """나스닥 선물(NQ=F) 항목. 본장이면 본장 세션, 아니면 야간 세션의 변동을 함께 돌려준다.

    추가 키:
        basis           항상 "futures"
        session         "regular"(본장 09:30~16:00 ET) / "night"(그 외·주말)
        session_start   세션 시작 시각(ET, ISO 문자열)
        session_change  세션 시작 대비 변동률(0.01 = 1%). 봉이 없으면 None
    daily_change 는 일봉 기준(직전 정산가 대비, CME 세션 경계 ET 18:00)이다.
    """
    et = to_eastern(now)
    closes = _fetch_closes(NASDAQ_FUTURES)
    entry = (
        _build_entry(NASDAQ_NAME, NASDAQ_FUTURES, closes)
        if closes is not None
        else _empty_entry(NASDAQ_NAME, NASDAQ_FUTURES)
    )
    window_start = session_window_start(et)
    return {
        **entry,
        "basis": "futures",
        "session": nasdaq_session(et),
        "session_start": window_start.isoformat(),
        "session_change": _fetch_session_change(window_start),
    }


def get_macro_indicators(now: datetime | None = None) -> list[dict]:
    """매크로 지표 9종을 조회한다 (나스닥은 선물).

    각 항목은 다음 키를 가진 dict:
        name, symbol, price, daily_change, weekly_change, is_point_diff.

    ``daily_change`` / ``weekly_change`` 는 일반 티커에서는 비율(0.01 = 1%),
    VIX / 채권 금리에서는 포인트 차이(``is_point_diff=True``)이다.

    "나스닥선물" 항목은 본장·야간을 가리지 않고 선물(NQ=F)을 쓰며
    ``session`` ("regular"/"night"), ``session_start``, ``session_change``(세션 시작 대비
    변동률), ``basis`` ("futures") 키가 추가된다. 한국 장중에는 야간 세션 변동이,
    미국 본장 중에는 본장 세션 변동이 들어간다. 선물의 ``daily_change`` 는 직전 정산가
    대비(세션 경계 ET 18:00)다.
    ``now`` 를 주면 그 시각 기준으로 판정한다 (기본: 현재 시각. naive 는 로컬 시각).

    신선도가 중요하므로 캐시하지 않는다.
    rate limit 준수를 위해 티커마다 1초 대기한다.
    """
    results: list[dict] = []

    for name, symbol in MACRO_TICKERS.items():
        try:
            if name == NASDAQ_NAME:
                results.append(_fetch_nasdaq(now))
                continue
            closes = _fetch_closes(symbol)
            if closes is None:
                results.append(_empty_entry(name, symbol))
            else:
                results.append(_build_entry(name, symbol, closes))
        except Exception as e:
            print(f"[yahoo_client] 매크로 지표 {name} 조회 실패: {e}")
            continue

    return results
