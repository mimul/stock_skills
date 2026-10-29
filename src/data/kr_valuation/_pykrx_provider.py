"""pykrx 공급자: KRX 정보데이터시스템 전종목 밸류에이션 스냅샷.

pykrx 1.2+ 는 KRX 로그인이 필요하다. ``KRX_ID`` / ``KRX_PW`` 환경 변수가
모두 설정되어 있고 pykrx 가 설치된 경우에만 활성화된다(둘 중 하나라도 없으면
import 조차 하지 않는다 — pykrx 는 import 시점에 로그인 실패 메시지를 출력한다).

스냅샷은 거래일 단위로 ``data/cache/kr_valuation_pykrx_YYYYMMDD.json`` 에
저장한다. 오늘 데이터가 비어 있으면(휴장·장 마감 전) 최대 7일 전까지
거슬러 올라가 가장 최근 거래일 스냅샷을 쓴다.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.data.yahoo_client import (
    _cache,  # CACHE_DIR 은 테스트에서 패치되므로 모듈 경유로 참조
)

NAME = "pykrx"
ENV_ID = "KRX_ID"
ENV_PW = "KRX_PW"
SNAPSHOT_PREFIX = "kr_valuation_pykrx_"
MAX_LOOKBACK_DAYS = 7
MARKETS = ("KOSPI", "KOSDAQ")

KST = ZoneInfo("Asia/Seoul")

# 세션 내 상태 (테스트는 reset_state() 로 초기화한다)
_empty_dates: set[str] = set()          # 비어 있던 날짜를 반복 조회하지 않는다
_snapshot_memo: dict[str, dict] = {}     # 날짜 → 스냅샷 (전종목 JSON 재파싱 방지)
_session_failed = False                  # 조회 예외 후 세션 동안 공급자 비활성화


def reset_state() -> None:
    """세션 상태 초기화 (테스트·자격 증명 교체 시)."""
    global _session_failed
    _empty_dates.clear()
    _snapshot_memo.clear()
    _session_failed = False


def is_available() -> bool:
    """KRX 자격 증명과 pykrx 설치가 모두 있고, 이번 세션에서 실패한 적이 없을 때만 True."""
    if _session_failed:
        return False
    if not (os.environ.get(ENV_ID) and os.environ.get(ENV_PW)):
        return False
    return importlib.util.find_spec("pykrx") is not None


def _snapshot_path(date_str: str):
    return _cache.CACHE_DIR / f"{SNAPSHOT_PREFIX}{date_str}.json"


def _to_float(value, keep_zero: bool = False) -> float | None:
    """NaN·변환 불가 값은 None. 0 은 기본적으로 None (KRX 는 적자 PER/PBR 을 0 으로 표기).

    배당(DIV/DPS)은 0 이 '무배당'이라는 정보이므로 ``keep_zero=True`` 로 유지한다.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or (f == 0 and not keep_zero):
        return None
    return f


def _fetch_snapshot(date_str: str) -> dict[str, dict]:
    """pykrx 로 코스피·코스닥 전종목 PER/PBR/EPS/BPS/DIV/DPS 를 받는다."""
    from pykrx import stock  # 지연 import: 자격 증명이 있을 때만

    snapshot: dict[str, dict] = {}
    for market in MARKETS:
        df = stock.get_market_fundamental_by_ticker(date_str, market=market)
        if df is None or df.empty:
            continue
        for code, row in df.iterrows():
            div = _to_float(row.get("DIV"), keep_zero=True)
            snapshot[str(code)] = {
                "per": _to_float(row.get("PER")),
                "pbr": _to_float(row.get("PBR")),
                "eps": _to_float(row.get("EPS")),
                "bps": _to_float(row.get("BPS")),
                "dividend_yield": div / 100.0 if div is not None else None,
                "dps": _to_float(row.get("DPS"), keep_zero=True),
                "market": market,
            }
    return snapshot


def _read_snapshot_file(date_str: str) -> dict[str, dict] | None:
    path = _snapshot_path(date_str)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data else None
    except (json.JSONDecodeError, ValueError):
        return None


def _write_snapshot_file(date_str: str, snapshot: dict[str, dict]) -> None:
    _cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_snapshot_path(date_str), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)


def load_snapshot(today: date | None = None) -> tuple[str, dict[str, dict]] | None:
    """가장 최근 거래일의 전종목 스냅샷을 (YYYY-MM-DD, {code: 지표}) 로 돌려준다.

    메모리 memo → 파일 캐시 → pykrx 조회 순으로 시도하고, 비어 있으면 하루씩 거슬러 올라간다.
    조회 예외가 나면 세션 동안 공급자를 비활성화한다(반복 실패·오류 출력 방지).
    """
    global _session_failed
    base = today or datetime.now(KST).date()
    for back in range(MAX_LOOKBACK_DAYS + 1):
        d = base - timedelta(days=back)
        key = d.strftime("%Y%m%d")
        if key in _empty_dates:
            continue
        if key in _snapshot_memo:
            return d.isoformat(), _snapshot_memo[key]
        cached = _read_snapshot_file(key)
        if cached:
            _snapshot_memo[key] = cached
            return d.isoformat(), cached
        try:
            fetched = _fetch_snapshot(key)
        except Exception as e:
            _session_failed = True
            print(f"[kr_valuation] pykrx 조회 실패 ({key}): {e} — 이번 세션에서는 yfinance 계산으로 대체합니다")
            return None
        if fetched:
            _write_snapshot_file(key, fetched)
            _snapshot_memo[key] = fetched
            return d.isoformat(), fetched
        _empty_dates.add(key)
    return None


def get(symbol: str, ticker=None) -> dict | None:
    """심볼(005930.KS)의 밸류에이션을 스냅샷에서 찾는다. 없으면 None. *ticker* 는 미사용(인터페이스 통일)."""
    loaded = load_snapshot()
    if loaded is None:
        return None
    as_of, snapshot = loaded
    entry = snapshot.get(symbol.split(".")[0])
    if not entry:
        return None
    return {**entry, "symbol": symbol, "as_of": as_of, "source": NAME}
