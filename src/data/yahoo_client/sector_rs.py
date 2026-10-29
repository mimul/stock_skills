"""섹터 상대강도(Relative Strength) — 한국 섹터 ETF 의 KODEX 200 대비 강약을 계산.

중규모 이상 PF 에서 사용. 소규모 PF 에서는 불필요.
RS = (섹터 ETF / KODEX 200 수익률 비) 로 시장 대비 강약을 정량화한다.
"""

from __future__ import annotations

from typing import Optional

from .history import get_price_history


# 한국 대표 섹터 ETF (KOSPI 상장). yfinance 조회 검증 완료 (2026-10-28)
SECTOR_ETFS: dict[str, str] = {
    "반도체": "091160.KS",       # KODEX 반도체
    "은행": "091170.KS",         # KODEX 은행
    "자동차": "091180.KS",       # KODEX 자동차
    "증권": "102970.KS",         # KODEX 증권
    "건설": "117700.KS",         # KODEX 건설
    "철강": "117680.KS",         # KODEX 철강
    "에너지화학": "117460.KS",   # KODEX 에너지화학
    "헬스케어": "266420.KS",     # KODEX 헬스케어
    "보험": "140700.KS",         # KODEX 보험
    "운송": "140710.KS",         # KODEX 운송
    "IT": "139260.KS",           # TIGER 200 IT
}

BENCHMARK = "069500.KS"  # KODEX 200


def get_sector_rs(period: str = "6mo") -> Optional[list[dict]]:
    """전체 섹터 ETF 의 상대강도(RS)를 계산해 RS 내림차순으로 반환한다.

    RS = (섹터 ETF / 벤치마크 20일 수익률 비) * 0.4
       + (섹터 ETF / 벤치마크 60일 수익률 비) * 0.4
       + (섹터 ETF 거래량 변화율)              * 0.2

    Parameters
    ----------
    period : str
        get_price_history 에 넘길 기간. 60일 수익률 계산에 "6mo" 필요.

    Returns
    -------
    list[dict] or None
        RS 내림차순 목록. 조회 실패 시 None.
        각 요소:
        {
            "name": "반도체",
            "symbol": "091160.KS",
            "rs_score": 1.15,
            "return_20d": 0.05,
            "return_60d": 0.12,
            "volume_change": 0.10,
            "rank": 1,
        }
    """
    # 벤치마크 조회
    bench_df = get_price_history(BENCHMARK, period=period)
    if bench_df is None or len(bench_df) < 60:
        return None

    bench_close = bench_df["Close"]
    bench_ret_20d = _safe_return(bench_close, 20)
    bench_ret_60d = _safe_return(bench_close, 60)

    if bench_ret_20d is None or bench_ret_60d is None:
        return None

    results: list[dict] = []

    for name, symbol in SECTOR_ETFS.items():
        df = get_price_history(symbol, period=period)
        if df is None or len(df) < 60:
            continue

        close = df["Close"]
        ret_20d = _safe_return(close, 20)
        ret_60d = _safe_return(close, 60)

        if ret_20d is None or ret_60d is None:
            continue

        # 거래량 변화율 (20일 평균 / 60일 평균 - 1)
        vol = df.get("Volume")
        vol_change = 0.0
        if vol is not None and len(vol) >= 60:
            vol_20 = vol.iloc[-20:].mean()
            vol_60 = vol.iloc[-60:].mean()
            if vol_60 > 0:
                vol_change = vol_20 / vol_60 - 1.0

        # RS 계산 (0 나눗셈 가드)
        rs_20d = ret_20d / bench_ret_20d if abs(bench_ret_20d) > 1e-6 else 1.0
        rs_60d = ret_60d / bench_ret_60d if abs(bench_ret_60d) > 1e-6 else 1.0

        rs_score = rs_20d * 0.4 + rs_60d * 0.4 + vol_change * 0.2

        results.append({
            "name": name,
            "symbol": symbol,
            "rs_score": round(rs_score, 3),
            "return_20d": round(ret_20d, 4),
            "return_60d": round(ret_60d, 4),
            "volume_change": round(vol_change, 4),
        })

    # RS 내림차순 정렬 + rank 부여
    results.sort(key=lambda x: -x["rs_score"])
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results if results else None


def _safe_return(series, days: int) -> Optional[float]:
    """N일 수익률을 안전하게 계산한다."""
    if len(series) < days + 1:
        return None
    current = float(series.iloc[-1])
    past = float(series.iloc[-days])
    if past == 0:
        return None
    return current / past - 1.0
