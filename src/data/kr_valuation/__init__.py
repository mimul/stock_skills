"""한국 종목 밸류에이션 보강 (PER/PBR/EPS/BPS).

Yahoo Finance 는 한국 종목의 PER/PBR/EPS/BPS 를 주지 않으므로, 공급자를
우선순위대로 시도해 공백을 메운다.

1. ``pykrx``        — KRX 전종목 일별 스냅샷. ``KRX_ID``/``KRX_PW`` 와 pykrx 설치 필요
2. ``yfinance-ttm`` — 분기 재무제표로 직접 계산한 TTM 값. 항상 사용 가능

공개 API
--------
- ``get_valuation(symbol)``      : {per, pbr, eps, bps, source, as_of, ...} 또는 None
- ``enrich_stock_info(info)``    : stock_info dict 의 빈 per/pbr 를 채운 **새 dict** 반환
- ``active_providers()``         : 현재 사용 가능한 공급자 이름 목록
"""

from __future__ import annotations

from typing import Any

from src.data.kr_valuation import _pykrx_provider, _yfinance_provider
from src.data.ticker_utils import is_korean_stock

# 우선순위 순
PROVIDERS = (_pykrx_provider, _yfinance_provider)
VALUATION_KEYS = ("per", "pbr", "eps", "bps")
NON_EQUITY_QUOTE_TYPES = frozenset({"ETF", "MUTUALFUND"})


def active_providers() -> list[str]:
    """현재 환경에서 사용 가능한 공급자 이름을 우선순위 순으로 돌려준다."""
    return [p.NAME for p in PROVIDERS if p.is_available()]


def _has_any_value(valuation: dict | None) -> bool:
    return bool(valuation) and any(valuation.get(k) is not None for k in VALUATION_KEYS)


def get_valuation(symbol: str, ticker: Any = None) -> dict | None:
    """한국 종목의 밸류에이션을 공급자 우선순위대로 조회한다.

    한국 종목이 아니면 None. 공급자가 네 지표 중 하나라도 주면 그 결과를 쓴다.
    *ticker* 는 이미 만들어 둔 ``yf.Ticker`` 객체(중복 조회 방지용, 선택).
    """
    if not is_korean_stock(symbol):
        return None
    for provider in PROVIDERS:
        if not provider.is_available():
            continue
        try:
            valuation = provider.get(symbol, ticker=ticker)
        except Exception as e:
            print(f"[kr_valuation] {provider.NAME} 조회 실패 ({symbol}): {e}")
            continue
        if _has_any_value(valuation):
            return valuation
    return None


def enrich_stock_info(info: dict, ticker: Any = None) -> dict:
    """stock_info dict 의 per/pbr 가 비어 있으면 채운 새 dict 를 돌려준다.

    - 입력 dict 는 변경하지 않는다
    - 한국 종목이 아니거나 per/pbr 가 이미 모두 있으면 값은 그대로 두고
      ``valuation_source`` 만 표기한다
    - 보강 시 ``eps`` / ``bps`` / ``valuation_source`` / ``valuation_as_of`` 를 추가한다
    """
    enriched = dict(info)
    symbol = enriched.get("symbol") or ""
    if not is_korean_stock(symbol):
        return enriched
    enriched.setdefault("eps", None)
    enriched.setdefault("bps", None)
    enriched.setdefault("valuation_source", None)
    enriched.setdefault("valuation_as_of", None)

    if (enriched.get("quoteType") or "").upper() in NON_EQUITY_QUOTE_TYPES:
        # ETF·펀드는 재무제표가 없어 PER/PBR 계산이 무의미하다. 요청 낭비를 막는다
        return enriched

    if enriched.get("per") is not None and enriched.get("pbr") is not None:
        enriched["valuation_source"] = enriched["valuation_source"] or "yahoo"
        return enriched

    valuation = get_valuation(symbol, ticker=ticker)
    if valuation is None:
        return enriched

    for key in VALUATION_KEYS:
        if enriched.get(key) is None and valuation.get(key) is not None:
            enriched[key] = valuation[key]
    enriched["valuation_source"] = valuation.get("source")
    enriched["valuation_as_of"] = valuation.get("as_of")
    return enriched


__all__ = [
    "PROVIDERS",
    "VALUATION_KEYS",
    "active_providers",
    "enrich_stock_info",
    "get_valuation",
]
