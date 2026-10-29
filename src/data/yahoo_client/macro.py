"""매크로 경제 지표 (KIK-396, KIK-449)."""

import time

import yfinance as yf


MACRO_TICKERS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P500": "^GSPC",
    "VIX": "^VIX",
    "미국10년물": "^TNX",
    "USD/KRW": "KRW=X",
    "WTI": "CL=F",
    "금": "GC=F",
}

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


def get_macro_indicators() -> list[dict]:
    """매크로 지표 8종을 조회한다.

    각 항목은 다음 키를 가진 dict:
        name, symbol, price, daily_change, weekly_change, is_point_diff.

    ``daily_change`` / ``weekly_change`` 는 일반 티커에서는 비율(0.01 = 1%),
    VIX / 채권 금리에서는 포인트 차이(``is_point_diff=True``)이다.

    신선도가 중요하므로 캐시하지 않는다.
    rate limit 준수를 위해 티커마다 1초 대기한다.
    """
    results: list[dict] = []

    for name, symbol in MACRO_TICKERS.items():
        try:
            time.sleep(1)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if hist is None or hist.empty or "Close" not in hist.columns:
                results.append(_empty_entry(name, symbol))
                continue

            closes = hist["Close"].dropna()
            if len(closes) == 0:
                results.append(_empty_entry(name, symbol))
                continue

            latest = float(closes.iloc[-1])
            is_point = symbol in _POINT_DIFF_TICKERS

            # 일간 변화
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

            results.append({
                "name": name,
                "symbol": symbol,
                "price": latest,
                "daily_change": daily_change,
                "weekly_change": weekly_change,
                "is_point_diff": is_point,
            })
        except Exception as e:
            print(f"[yahoo_client] 매크로 지표 {name} 조회 실패: {e}")
            continue

    return results
