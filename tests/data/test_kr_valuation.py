"""src.data.kr_valuation 테스트 (공급자 우선순위·보강·pykrx 스냅샷)."""

import json
import sys
import types
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data import kr_valuation
from src.data.kr_valuation import _pykrx_provider, _yfinance_provider

_CACHE_DIR_PATCH = "src.data.yahoo_client._cache.CACHE_DIR"


@pytest.fixture(autouse=True)
def _no_krx_credentials(monkeypatch):
    monkeypatch.delenv(_pykrx_provider.ENV_ID, raising=False)
    monkeypatch.delenv(_pykrx_provider.ENV_PW, raising=False)
    _pykrx_provider.reset_state()


@pytest.fixture
def cache_dir(tmp_path):
    with patch(_CACHE_DIR_PATCH, tmp_path):
        yield tmp_path


# ===================================================================
# 공급자 선택
# ===================================================================

class TestProviderSelection:
    def test_without_credentials_only_yfinance(self):
        assert kr_valuation.active_providers() == ["yfinance-ttm"]

    def test_pykrx_requires_both_env_and_package(self, monkeypatch):
        monkeypatch.setenv("KRX_ID", "id")
        assert _pykrx_provider.is_available() is False  # PW 없음
        monkeypatch.setenv("KRX_PW", "pw")
        with patch("src.data.kr_valuation._pykrx_provider.importlib.util.find_spec", return_value=None):
            assert _pykrx_provider.is_available() is False  # 미설치
        with patch("src.data.kr_valuation._pykrx_provider.importlib.util.find_spec", return_value=object()):
            assert _pykrx_provider.is_available() is True
            assert kr_valuation.active_providers() == ["pykrx", "yfinance-ttm"]


# ===================================================================
# get_valuation
# ===================================================================

class TestGetValuation:
    def test_non_korean_symbol_returns_none(self):
        with patch.object(_yfinance_provider, "get", side_effect=AssertionError("호출되면 안 됨")):
            assert kr_valuation.get_valuation("AAPL") is None

    def test_falls_through_to_next_provider_when_empty(self, monkeypatch):
        monkeypatch.setattr(_pykrx_provider, "is_available", lambda: True)
        monkeypatch.setattr(_pykrx_provider, "get", lambda s, ticker=None: {"per": None, "pbr": None, "eps": None, "bps": None})
        monkeypatch.setattr(_yfinance_provider, "get", lambda s, ticker=None: {"per": 9.0, "pbr": 1.1, "source": "yfinance-ttm"})
        assert kr_valuation.get_valuation("005930.KS")["source"] == "yfinance-ttm"

    def test_first_provider_wins(self, monkeypatch):
        monkeypatch.setattr(_pykrx_provider, "is_available", lambda: True)
        monkeypatch.setattr(_pykrx_provider, "get", lambda s, ticker=None: {"per": 8.0, "pbr": None, "source": "pykrx"})
        monkeypatch.setattr(_yfinance_provider, "get", lambda s, ticker=None: {"per": 9.0, "pbr": 1.1, "source": "yfinance-ttm"})
        assert kr_valuation.get_valuation("005930.KS")["source"] == "pykrx"

    def test_provider_exception_is_skipped(self, monkeypatch):
        monkeypatch.setattr(_pykrx_provider, "is_available", lambda: True)
        monkeypatch.setattr(_pykrx_provider, "get", MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(_yfinance_provider, "get", lambda s, ticker=None: {"per": 9.0, "source": "yfinance-ttm"})
        assert kr_valuation.get_valuation("247540.KQ")["per"] == 9.0

    def test_ticker_is_passed_to_provider(self, monkeypatch):
        seen = {}

        def fake_get(symbol, ticker=None):
            seen['ticker'] = ticker
            return {'per': 1.0, 'source': 'yfinance-ttm'}

        monkeypatch.setattr(_yfinance_provider, 'get', fake_get)
        sentinel = object()
        kr_valuation.get_valuation('005930.KS', ticker=sentinel)
        assert seen['ticker'] is sentinel

    def test_all_providers_empty(self, monkeypatch):
        monkeypatch.setattr(_yfinance_provider, "get", lambda s, ticker=None: None)
        assert kr_valuation.get_valuation("005930.KS") is None


# ===================================================================
# enrich_stock_info
# ===================================================================

class TestEnrichStockInfo:
    def test_fills_missing_per_pbr_without_mutating_input(self, monkeypatch):
        monkeypatch.setattr(kr_valuation, "get_valuation", lambda s, ticker=None: {
            "per": 8.85, "pbr": 2.34, "eps": 26213.0, "bps": 98968.0, "source": "yfinance-ttm", "as_of": "2026-06-30",
        })
        info = {"symbol": "005930.KS", "per": None, "pbr": None, "price": 232000}
        out = kr_valuation.enrich_stock_info(info)
        assert out["per"] == 8.85 and out["pbr"] == 2.34
        assert out["eps"] == 26213.0 and out["bps"] == 98968.0
        assert out["valuation_source"] == "yfinance-ttm"
        assert out["valuation_as_of"] == "2026-06-30"
        assert info == {"symbol": "005930.KS", "per": None, "pbr": None, "price": 232000}  # 불변

    def test_keeps_existing_yahoo_values(self, monkeypatch):
        monkeypatch.setattr(kr_valuation, "get_valuation", MagicMock(side_effect=AssertionError("호출되면 안 됨")))
        out = kr_valuation.enrich_stock_info({"symbol": "005930.KS", "per": 10.0, "pbr": 1.5})
        assert out["per"] == 10.0 and out["pbr"] == 1.5
        assert out["valuation_source"] == "yahoo"

    def test_partial_fill_only_missing_keys(self, monkeypatch):
        monkeypatch.setattr(kr_valuation, "get_valuation", lambda s, ticker=None: {"per": 8.0, "pbr": 2.0, "eps": 1.0, "bps": 2.0, "source": "pykrx", "as_of": "2026-10-28"})
        out = kr_valuation.enrich_stock_info({"symbol": "005930.KS", "per": None, "pbr": 1.5})
        assert out["per"] == 8.0
        assert out["pbr"] == 1.5  # 기존 값 유지
        assert out["valuation_source"] == "pykrx"

    def test_us_symbol_untouched(self, monkeypatch):
        monkeypatch.setattr(kr_valuation, "get_valuation", MagicMock(side_effect=AssertionError("호출되면 안 됨")))
        info = {"symbol": "AAPL", "per": None, "pbr": None}
        assert kr_valuation.enrich_stock_info(info) == info

    def test_etf_is_not_enriched(self, monkeypatch):
        """ETF 는 재무제표가 없으므로 공급자를 호출하지 않는다 (M5)."""
        monkeypatch.setattr(kr_valuation, "get_valuation", MagicMock(side_effect=AssertionError("호출되면 안 됨")))
        out = kr_valuation.enrich_stock_info({"symbol": "069500.KS", "per": None, "pbr": None, "quoteType": "ETF"})
        assert out["per"] is None and out["valuation_source"] is None

    def test_no_valuation_leaves_none_with_keys(self, monkeypatch):
        monkeypatch.setattr(kr_valuation, "get_valuation", lambda s, ticker=None: None)
        out = kr_valuation.enrich_stock_info({"symbol": "247540.KQ", "per": None, "pbr": None})
        assert out["per"] is None and out["valuation_source"] is None
        assert "eps" in out and "bps" in out


# ===================================================================
# pykrx 공급자 (가짜 pykrx 모듈 주입)
# ===================================================================

def _install_fake_pykrx(monkeypatch, frames_by_date: dict[str, dict[str, pd.DataFrame]], calls: list):
    """sys.modules 에 가짜 pykrx.stock 을 넣는다. frames_by_date[date][market] → DataFrame."""
    stock = types.SimpleNamespace()

    def get_market_fundamental_by_ticker(date_str, market="KOSPI"):
        calls.append((date_str, market))
        return frames_by_date.get(date_str, {}).get(market, pd.DataFrame())

    stock.get_market_fundamental_by_ticker = get_market_fundamental_by_ticker
    pykrx = types.ModuleType("pykrx")
    pykrx.stock = stock
    monkeypatch.setitem(sys.modules, "pykrx", pykrx)
    monkeypatch.setitem(sys.modules, "pykrx.stock", stock)


def _frame(rows: dict[str, list]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient="index", columns=["BPS", "PER", "PBR", "EPS", "DIV", "DPS"])


class TestPykrxProvider:
    def test_snapshot_parsed_and_cached(self, monkeypatch, cache_dir):
        calls: list = []
        _install_fake_pykrx(monkeypatch, {
            "20261028": {
                "KOSPI": _frame({"005930": [98968, 8.85, 2.34, 26213, 1.6, 1444]}),
                "KOSDAQ": _frame({"086890": [2908, 0, 1.2, -200, 0, 0]}),
            },
        }, calls)
        loaded = _pykrx_provider.load_snapshot(today=date(2026, 10, 28))
        as_of, snap = loaded
        assert as_of == "2026-10-28"
        assert snap["005930"]["per"] == 8.85
        assert snap["005930"]["dividend_yield"] == pytest.approx(0.016)
        assert snap["005930"]["market"] == "KOSPI"
        # KRX 의 PER 0 은 적자 → None. 배당 0 은 '무배당' 정보이므로 0.0 유지
        assert snap["086890"]["per"] is None
        assert snap["086890"]["dividend_yield"] == 0.0 and snap["086890"]["dps"] == 0.0
        assert (cache_dir / "kr_valuation_pykrx_20261028.json").exists()
        # 두 번째 로드는 파일 캐시에서 (pykrx 재호출 없음)
        n = len(calls)
        _pykrx_provider.load_snapshot(today=date(2026, 10, 28))
        assert len(calls) == n

    def test_lookback_to_previous_trading_day(self, monkeypatch, cache_dir):
        calls: list = []
        _install_fake_pykrx(monkeypatch, {
            "20261024": {"KOSPI": _frame({"005930": [1, 2, 3, 4, 5, 6]})},
        }, calls)
        as_of, snap = _pykrx_provider.load_snapshot(today=date(2026, 10, 26))  # 일요일
        assert as_of == "2026-10-24"
        assert "005930" in snap
        assert "20261026" in _pykrx_provider._empty_dates and "20261025" in _pykrx_provider._empty_dates

    def test_no_data_within_lookback_returns_none(self, monkeypatch, cache_dir):
        _install_fake_pykrx(monkeypatch, {}, [])
        assert _pykrx_provider.load_snapshot(today=date(2026, 10, 28)) is None

    def test_get_maps_symbol_to_code(self, monkeypatch, cache_dir):
        monkeypatch.setattr(_pykrx_provider, "load_snapshot", lambda today=None: ("2026-10-28", {"247540": {"per": 50.0, "pbr": 4.7, "eps": 400, "bps": 10000, "dividend_yield": None, "dps": None, "market": "KOSDAQ"}}))
        v = _pykrx_provider.get("247540.KQ")
        assert v["symbol"] == "247540.KQ" and v["source"] == "pykrx" and v["as_of"] == "2026-10-28"
        assert _pykrx_provider.get("000000.KS") is None

    def test_fetch_error_returns_none(self, monkeypatch, cache_dir):
        stock = types.SimpleNamespace(get_market_fundamental_by_ticker=MagicMock(side_effect=RuntimeError("login")))
        pykrx = types.ModuleType("pykrx"); pykrx.stock = stock
        monkeypatch.setitem(sys.modules, "pykrx", pykrx)
        monkeypatch.setitem(sys.modules, "pykrx.stock", stock)
        assert _pykrx_provider.load_snapshot(today=date(2026, 10, 28)) is None
        # 실패 후에는 세션 동안 공급자가 비활성화되어 재시도·오류 출력을 반복하지 않는다 (M6)
        monkeypatch.setenv("KRX_ID", "id"); monkeypatch.setenv("KRX_PW", "pw")
        with patch("src.data.kr_valuation._pykrx_provider.importlib.util.find_spec", return_value=object()):
            assert _pykrx_provider.is_available() is False
            _pykrx_provider.reset_state()
            assert _pykrx_provider.is_available() is True

    def test_snapshot_memo_avoids_reparsing(self, monkeypatch, cache_dir):
        _install_fake_pykrx(monkeypatch, {"20261028": {"KOSPI": _frame({"005930": [1, 2, 3, 4, 5, 6]})}}, [])
        _pykrx_provider.load_snapshot(today=date(2026, 10, 28))
        (cache_dir / "kr_valuation_pykrx_20261028.json").unlink()
        as_of, snap = _pykrx_provider.load_snapshot(today=date(2026, 10, 28))
        assert as_of == "2026-10-28" and snap["005930"]["per"] == 2.0

    def test_corrupt_cache_file_is_refetched(self, monkeypatch, cache_dir):
        (cache_dir / "kr_valuation_pykrx_20261028.json").write_text("{not json", encoding="utf-8")
        calls: list = []
        _install_fake_pykrx(monkeypatch, {"20261028": {"KOSPI": _frame({"005930": [1, 2, 3, 4, 5, 6]})}}, calls)
        as_of, _ = _pykrx_provider.load_snapshot(today=date(2026, 10, 28))
        assert as_of == "2026-10-28" and calls
        assert json.loads((cache_dir / "kr_valuation_pykrx_20261028.json").read_text())["005930"]["per"] == 2.0


# ===================================================================
# get_stock_info 연결
# ===================================================================

class TestGetStockInfoIntegration:
    def _fake_ticker(self, info):
        t = MagicMock(); t.info = info
        return t

    def test_korean_symbol_is_enriched_before_cache(self, monkeypatch, cache_dir):
        from src.data.yahoo_client import detail
        monkeypatch.setattr(detail.yf, "Ticker", lambda s: self._fake_ticker({"regularMarketPrice": 232000, "currency": "KRW"}))
        monkeypatch.setattr(kr_valuation, "get_valuation", lambda s, ticker=None: {"per": 8.85, "pbr": 2.34, "eps": 1.0, "bps": 2.0, "source": "yfinance-ttm", "as_of": "2026-06-30"})
        info = detail.get_stock_info("005930.KS")
        assert info["per"] == 8.85 and info["pbr"] == 2.34 and info["valuation_source"] == "yfinance-ttm"
        cached = json.loads((cache_dir / "005930_KS.json").read_text())
        assert cached["per"] == 8.85

    def test_mocked_ticker_reused_without_network(self, monkeypatch, cache_dir):
        """get_stock_info 가 만든 Ticker 를 TTM 계산에 재사용한다 (yf.Ticker 2회 호출 없음)."""
        from src.data.yahoo_client import detail, kr_fundamentals
        t = self._fake_ticker({'regularMarketPrice': 100.0, 'currentPrice': 100.0, 'sharesOutstanding': 10, 'currency': 'KRW'})
        cols = pd.to_datetime(['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30'])
        t.quarterly_financials = pd.DataFrame([[10.0, 10.0, 10.0, 10.0]], index=['Net Income'], columns=cols)
        t.quarterly_balance_sheet = pd.DataFrame([[200.0]], index=['Stockholders Equity'], columns=cols[:1])
        # detail.yf 와 kr_fundamentals.yf 는 같은 yfinance 모듈이므로 호출 횟수로 재사용을 검증한다
        ticker_factory = MagicMock(return_value=t)
        monkeypatch.setattr(detail.yf, 'Ticker', ticker_factory)
        assert kr_fundamentals.yf.Ticker is ticker_factory
        info = detail.get_stock_info('005930.KS')
        assert info['per'] == 25.0 and info['pbr'] == 5.0 and info['valuation_source'] == 'yfinance-ttm'
        assert ticker_factory.call_count == 1

    def test_us_symbol_not_enriched(self, monkeypatch, cache_dir):
        from src.data.yahoo_client import detail
        monkeypatch.setattr(detail.yf, "Ticker", lambda s: self._fake_ticker({"regularMarketPrice": 100, "trailingPE": 30.0}))
        monkeypatch.setattr(kr_valuation, "get_valuation", MagicMock(side_effect=AssertionError("호출되면 안 됨")))
        info = detail.get_stock_info("AAPL")
        assert info["per"] == 30.0 and "valuation_source" not in info

    def test_anomaly_sanitized_after_enrichment(self, monkeypatch, cache_dir):
        from src.data.yahoo_client import detail
        monkeypatch.setattr(detail.yf, "Ticker", lambda s: self._fake_ticker({"regularMarketPrice": 1000}))
        monkeypatch.setattr(kr_valuation, "get_valuation", lambda s, ticker=None: {"per": 0.5, "pbr": 0.01, "eps": 1.0, "bps": 2.0, "source": "pykrx", "as_of": "2026-10-28"})
        info = detail.get_stock_info("005930.KS")
        assert info["per"] is None and info["pbr"] is None  # 0<per<1, pbr<0.05 는 이상값
