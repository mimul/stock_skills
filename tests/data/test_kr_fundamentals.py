"""src.data.yahoo_client.kr_fundamentals 테스트 (한국 종목 TTM PER/PBR 계산)."""

from unittest.mock import patch

import pandas as pd
import pytest

from src.data.yahoo_client import kr_fundamentals
from src.data.yahoo_client.kr_fundamentals import (
    SOURCE_NAME,
    _quarters_contiguous,
    _row_values,
    compute_ttm_valuation,
)

_CACHE_DIR_PATCH = "src.data.yahoo_client._cache.CACHE_DIR"


class _FakeTicker:
    """quarterly_financials / quarterly_balance_sheet / info 를 흉내 내는 객체."""

    def __init__(self, info, net_incomes=None, equity=None, income_row="Net Income", equity_row="Stockholders Equity", dates=None):
        self.info = info
        cols = pd.to_datetime(dates or ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"])
        self.quarterly_financials = (
            pd.DataFrame([net_incomes], index=[income_row], columns=cols[: len(net_incomes)])
            if net_incomes is not None else pd.DataFrame()
        )
        self.quarterly_balance_sheet = (
            pd.DataFrame([[equity]], index=[equity_row], columns=cols[:1])
            if equity is not None else pd.DataFrame()
        )


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path):
    with patch(_CACHE_DIR_PATCH, tmp_path):
        yield tmp_path


class TestRowValues:
    def test_latest_first_contiguous(self):
        df = pd.DataFrame([[4.0, 3.0, float("nan"), 1.0]], index=["Net Income"])
        assert _row_values(df, ("Net Income",), 4) == [4.0, 3.0]

    def test_first_matching_row_wins(self):
        df = pd.DataFrame([[1.0], [2.0]], index=["Net Income", "Net Income Common Stockholders"])
        assert _row_values(df, ("Net Income Common Stockholders", "Net Income"), 1) == [2.0]

    def test_non_dataframe_returns_empty(self):
        assert _row_values(None, ("x",), 4) == []
        assert _row_values(object(), ("x",), 4) == []
        assert _row_values(pd.DataFrame(), ("x",), 4) == []


class TestComputeTtmValuation:
    def test_computes_per_pbr_from_statements(self):
        # 가상값: 주가 100, 주식수 10, 4분기 순이익 합 50 → EPS 5 → PER 20 / 자본 400 → BPS 40 → PBR 2.5
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 15.0, 12.0, 13.0], 400.0)
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["per"] == 20.0
        assert v["pbr"] == 2.5
        assert v["eps"] == 5.0
        assert v["bps"] == 40.0
        assert v["as_of"] == "2026-06-30"
        assert v["source"] == SOURCE_NAME

    def test_negative_ttm_earnings_gives_no_per_but_keeps_pbr(self):
        t = _FakeTicker({"sharesOutstanding": 10, "regularMarketPrice": 100.0}, [-10.0, -5.0, 2.0, 1.0], 400.0)
        v = compute_ttm_valuation("086890.KQ", ticker=t)
        assert v["per"] is None
        assert v["eps"] == -1.2
        assert v["pbr"] == 2.5

    def test_fewer_than_four_quarters_gives_no_eps(self):
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 15.0], 400.0)
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["eps"] is None and v["per"] is None
        assert v["pbr"] == 2.5

    def test_missing_shares_returns_none(self):
        t = _FakeTicker({"currentPrice": 100.0}, [1.0, 1.0, 1.0, 1.0], 400.0)
        assert compute_ttm_valuation("005930.KS", ticker=t) is None

    def test_missing_price_returns_none(self):
        t = _FakeTicker({"sharesOutstanding": 10}, [1.0, 1.0, 1.0, 1.0], 400.0)
        assert compute_ttm_valuation("005930.KS", ticker=t) is None

    def test_no_statements_returns_none(self):
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0})
        assert compute_ttm_valuation("005930.KS", ticker=t) is None

    def test_alternative_row_names(self):
        t = _FakeTicker(
            {"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 10.0, 10.0, 10.0], 200.0,
            income_row="Net Income Common Stockholders", equity_row="Total Equity Gross Minority Interest",
        )
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["per"] == 25.0 and v["pbr"] == 5.0

    def test_result_is_cached(self, _isolated_cache):
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 10.0, 10.0, 10.0], 200.0)
        compute_ttm_valuation("005930.KS", ticker=t)
        assert (_isolated_cache / "005930_KS_valuation.json").exists()
        # 두 번째 호출은 ticker 없이도 캐시에서 반환된다
        with patch.object(kr_fundamentals.yf, "Ticker", side_effect=AssertionError("네트워크 호출 금지")):
            v = compute_ttm_valuation("005930.KS")
        assert v["per"] == 25.0

    def test_exception_is_swallowed(self):
        class Broken:
            @property
            def info(self):
                raise RuntimeError("boom")
        assert compute_ttm_valuation("005930.KS", ticker=Broken()) is None


# ===================================================================
# 코드 리뷰 반영 회귀 테스트
# ===================================================================


def _dates(*ds):
    return pd.to_datetime(list(ds))


class TestPreferredShares:
    def test_preferred_symbol_is_skipped(self):
        """우선주(끝자리 5)는 회사 전체 이익/우선주 주식수로 EPS 가 왜곡되므로 계산하지 않는다 (H1)."""
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 10.0, 10.0, 10.0], 200.0)
        assert compute_ttm_valuation("005935.KS", ticker=t) is None
        assert compute_ttm_valuation("005930.KS", ticker=t)["per"] == 25.0


class TestQuarterContinuity:
    def test_gap_in_quarters_gives_no_eps(self):
        """Q4 가 빠진 4개 분기(9개월 초과 간격)는 TTM 으로 인정하지 않는다 (M1)."""
        t = _FakeTicker(
            {"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 10.0, 10.0, 10.0], 200.0,
            dates=["2026-06-30", "2026-03-31", "2025-09-30", "2025-06-30", "2025-03-31"],
        )
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["eps"] is None and v["per"] is None
        assert v["pbr"] == 5.0

    def test_contiguous_helper(self):
        ok = pd.DataFrame([[1, 1, 1, 1]], index=["x"], columns=_dates("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"))
        gap = pd.DataFrame([[1, 1, 1, 1]], index=["x"], columns=_dates("2026-06-30", "2026-03-31", "2025-09-30", "2025-06-30"))
        short = pd.DataFrame([[1, 1]], index=["x"], columns=_dates("2026-06-30", "2026-03-31"))
        assert _quarters_contiguous(ok) is True
        assert _quarters_contiguous(gap) is False
        assert _quarters_contiguous(short) is False


class TestColumnOrdering:
    def test_oldest_first_columns_are_sorted(self):
        """컬럼이 과거→최신 순이어도 최신 4분기로 계산하고 as_of 는 최신 분기다 (M2)."""
        t = _FakeTicker(
            {"sharesOutstanding": 10, "currentPrice": 100.0}, [1.0, 1.0, 1.0, 1.0, 100.0], 200.0,
            dates=["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"],
        )
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["as_of"] == "2026-06-30"
        assert v["eps"] == 10.3  # (100 + 1 + 1 + 1) / 10, 가장 오래된 1.0 은 제외


class TestRowFallback:
    def test_incomplete_first_row_falls_back_to_next(self):
        """첫 후보 행이 2분기뿐이면 4분기가 있는 다음 후보 행을 쓴다 (M3)."""
        cols = _dates("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30")
        df = pd.DataFrame(
            [[10.0, 10.0, float("nan"), float("nan")], [20.0, 20.0, 20.0, 20.0]],
            index=["Net Income Common Stockholders", "Net Income"], columns=cols,
        )
        assert _row_values(df, ("Net Income Common Stockholders", "Net Income"), 4, require_full=True) == [20.0] * 4
        assert _row_values(df, ("Net Income Common Stockholders", "Net Income"), 4) == [10.0, 10.0]

    def test_basic_eps_row_preferred_over_net_income(self):
        """Basic EPS 행이 있으면 순이익/주식수보다 우선한다 (M4)."""
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0, 10.0, 10.0, 10.0], 200.0)
        t.quarterly_financials.loc["Basic EPS"] = [2.0, 2.0, 2.0, 2.0]
        v = compute_ttm_valuation("005930.KS", ticker=t)
        assert v["eps"] == 8.0 and v["per"] == 12.5

    def test_na_values_detected_for_numpy_types(self):
        """pd.NA / numpy NaN 도 결측으로 본다 (L9)."""
        df = pd.DataFrame([[pd.NA, 1.0]], index=["x"], columns=_dates("2026-06-30", "2026-03-31"), dtype="object")
        assert _row_values(df, ("x",), 2) == []


class TestCurrencyGuard:
    def test_financial_currency_mismatch_returns_none(self):
        """재무제표 통화가 시세 통화와 다르면 계산하지 않는다 (M4)."""
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0, "currency": "KRW", "financialCurrency": "USD"}, [10.0] * 4, 200.0)
        assert compute_ttm_valuation("900270.KQ", ticker=t) is None

    def test_same_currency_passes(self):
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0, "currency": "KRW", "financialCurrency": "KRW"}, [10.0] * 4, 200.0)
        assert compute_ttm_valuation("005930.KS", ticker=t)["per"] == 25.0


class TestCacheMeta:
    def test_cache_hit_strips_cached_at(self, _isolated_cache):
        """캐시 hit 응답에도 _cached_at 이 섞이지 않는다 (L1)."""
        t = _FakeTicker({"sharesOutstanding": 10, "currentPrice": 100.0}, [10.0] * 4, 200.0)
        first = compute_ttm_valuation("005930.KS", ticker=t)
        second = compute_ttm_valuation("005930.KS")
        assert "_cached_at" not in first and "_cached_at" not in second
        assert first == second
