"""yfinance 공급자: 분기 재무제표로 계산한 TTM PER/PBR (자격 증명 불필요).

항상 사용 가능한 최종 폴백이다. 실제 계산은
``src.data.yahoo_client.kr_fundamentals.compute_ttm_valuation`` 이 담당한다
(yfinance 직접 호출은 yahoo_client 안에서만 한다는 규약).
"""

from __future__ import annotations

NAME = "yfinance-ttm"


def is_available() -> bool:
    return True


def get(symbol: str, ticker=None) -> dict | None:
    """*ticker* 는 이미 만들어 둔 yf.Ticker 객체(중복 조회 방지용, 선택)."""
    from src.data.yahoo_client.kr_fundamentals import (
        compute_ttm_valuation,  # 지연 import
    )

    return compute_ttm_valuation(symbol, ticker=ticker)
