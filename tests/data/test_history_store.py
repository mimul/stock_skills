"""Tests for src.data.history_store module."""

import json
import math
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from src.data.history import (
    _safe_filename,
    load_history,
    list_history_files,
    save_forecast,
    save_health,
    save_market_context,
    save_report,
    save_research,
    save_screening,
    save_stress_test,
    save_trade,
)


# ===================================================================
# Helpers
# ===================================================================

def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sample_results():
    return [
        {
            "symbol": "005930.KS",
            "name": "삼성전자",
            "price": 2850,
            "per": 10.5,
            "pbr": 0.95,
            "dividend_yield": 0.032,
            "roe": 0.12,
            "value_score": 72.5,
        },
        {
            "symbol": "AAPL",
            "name": "Apple Inc",
            "price": 175.0,
            "per": 28.0,
            "pbr": 45.0,
            "dividend_yield": 0.005,
            "roe": 1.5,
            "value_score": 35.0,
        },
    ]


def _sample_stock_data():
    return {
        "name": "삼성전자",
        "sector": "Technology",
        "industry": "Semiconductors",
        "price": 2850,
        "per": 10.5,
        "pbr": 0.95,
        "dividend_yield": 0.032,
        "roe": 0.12,
        "roa": 0.05,
        "revenue_growth": 0.08,
        "market_cap": 35000000000000,
    }


def _sample_health_data():
    return {
        "positions": [
            {
                "symbol": "005930.KS",
                "pnl_pct": 0.15,
                "trend_health": {"trend": "상승"},
                "change_quality": {"quality_label": "양호"},
                "alert": {"level": "none"},
            },
            {
                "symbol": "AAPL",
                "pnl_pct": -0.05,
                "trend_health": {"trend": "하락"},
                "change_quality": {"quality_label": "1개 지표 악화"},
                "alert": {"level": "caution"},
            },
        ],
        "summary": {
            "total": 2,
            "healthy": 1,
            "early_warning": 0,
            "caution": 1,
            "exit": 0,
        },
    }


# ===================================================================
# save_screening
# ===================================================================


class TestSaveScreening:
    def test_save_creates_file(self, tmp_path):
        path = save_screening("value", "kr", _sample_results(), base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        # KIK-743: HHMMSS 일의화 (같은 날 같은 region/preset 덮어쓰기 방지)
        path = save_screening("value", "kr", _sample_results(), base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename.startswith(f"{today}_kr_value_")
        assert filename.endswith(".json")

    def test_save_contains_metadata(self, tmp_path):
        path = save_screening("value", "kr", _sample_results(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "screen"
        assert data["preset"] == "value"
        assert data["region"] == "kr"
        assert data["date"] == date.today().isoformat()
        assert "_saved_at" in data
        assert "timestamp" in data

    def test_save_contains_results(self, tmp_path):
        results = _sample_results()
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["symbol"] == "005930.KS"
        assert data["results"][1]["symbol"] == "AAPL"

    def test_save_with_sector(self, tmp_path):
        path = save_screening("value", "kr", _sample_results(), sector="Technology", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["sector"] == "Technology"

    def test_save_without_sector(self, tmp_path):
        path = save_screening("value", "kr", _sample_results(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["sector"] is None

    def test_save_does_not_overwrite_same_day(self, tmp_path):
        # KIK-744: HHMMSSffffff + uuid 일의화로 같은 날 같은 region/preset 이라도
        # 별도 파일로 저장된다 (구 테스트는 덮어쓰기 전제였음).
        results1 = [{"symbol": "A", "value_score": 50}]
        results2 = [{"symbol": "B", "value_score": 60}]
        path1 = save_screening("value", "kr", results1, base_dir=str(tmp_path))
        path2 = save_screening("value", "kr", results2, base_dir=str(tmp_path))
        assert path1 != path2
        # 두 파일 모두 남아 있다
        data1 = _read_json(path1)
        data2 = _read_json(path2)
        assert data1["results"][0]["symbol"] == "A"
        assert data2["results"][0]["symbol"] == "B"

    def test_save_creates_screen_subdirectory(self, tmp_path):
        save_screening("value", "kr", [], base_dir=str(tmp_path))
        assert (tmp_path / "screen").is_dir()

    def test_save_region_with_dot(self, tmp_path):
        """Region containing dots should be safe in filename."""
        path = save_screening("value", "jp.asia", [], base_dir=str(tmp_path))
        filename = Path(path).name
        assert "." not in filename.split("_", 1)[1].replace(".json", "")


# ===================================================================
# save_report
# ===================================================================


class TestSaveReport:
    def test_save_creates_file(self, tmp_path):
        path = save_report("005930.KS", _sample_stock_data(), 72.5, "저평가", base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        # KIK-743: HHMMSS 일의화 (같은 날 같은 종목 덮어쓰기 방지)
        path = save_report("005930.KS", _sample_stock_data(), 72.5, "저평가", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename.startswith(f"{today}_005930_KS_")
        assert filename.endswith(".json")

    def test_save_contains_score_and_verdict(self, tmp_path):
        path = save_report("005930.KS", _sample_stock_data(), 72.5, "저평가(매수 검토)", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "report"
        assert data["symbol"] == "005930.KS"
        assert data["value_score"] == 72.5
        assert data["verdict"] == "저평가(매수 검토)"
        assert data["name"] == "삼성전자"
        assert data["sector"] == "Technology"

    def test_save_creates_report_subdirectory(self, tmp_path):
        save_report("AAPL", {}, 50.0, "중립", base_dir=str(tmp_path))
        assert (tmp_path / "report").is_dir()


# ===================================================================
# save_trade
# ===================================================================


class TestSaveTrade:
    def test_save_buy(self, tmp_path):
        path = save_trade("005930.KS", "buy", 100, 2850.0, "KRW", "2026-02-14", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "trade"
        assert data["trade_type"] == "buy"
        assert data["symbol"] == "005930.KS"
        assert data["shares"] == 100
        assert data["price"] == 2850.0
        assert data["currency"] == "KRW"

    def test_save_sell(self, tmp_path):
        path = save_trade("AAPL", "sell", 5, 180.0, "USD", "2026-02-14", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["trade_type"] == "sell"
        assert data["symbol"] == "AAPL"
        assert data["shares"] == 5

    def test_save_file_naming(self, tmp_path):
        # KIK-744: 파일명 끝에 HHMMSSffffff_<6hex> 가 붙는다 (같은 초 충돌 방지)
        path = save_trade("005930.KS", "buy", 100, 2850.0, "KRW", "2026-02-14", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        prefix = f"{today}_buy_005930_KS_"
        assert filename.startswith(prefix)
        assert filename.endswith(".json")
        suffix = filename[len(prefix):-len(".json")]
        # 형식: HHMMSSffffff_<6hex>
        assert len(suffix) == 19, f"unexpected suffix length: {suffix!r}"
        assert suffix[12] == "_"
        assert suffix[:12].isdigit()

    def test_save_sell_file_naming(self, tmp_path):
        # KIK-744: 파일명 끝에 HHMMSSffffff_<6hex> 가 붙는다 (같은 초 충돌 방지)
        path = save_trade("AAPL", "sell", 5, 180.0, "USD", "2026-02-14", base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        prefix = f"{today}_sell_AAPL_"
        assert filename.startswith(prefix)
        assert filename.endswith(".json")
        suffix = filename[len(prefix):-len(".json")]
        assert len(suffix) == 19, f"unexpected suffix length: {suffix!r}"
        assert suffix[12] == "_"
        assert suffix[:12].isdigit()

    def test_save_with_memo(self, tmp_path):
        path = save_trade("005930.KS", "buy", 100, 2850.0, "KRW", "2026-02-14", memo="저평가 구간 진입", base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["memo"] == "저평가 구간 진입"

    def test_save_creates_trade_subdirectory(self, tmp_path):
        save_trade("X", "buy", 1, 1.0, "USD", "2026-01-01", base_dir=str(tmp_path))
        assert (tmp_path / "trade").is_dir()

    # KIK-441: sell P&L 필드

    def test_save_sell_with_pnl_fields(self, tmp_path):
        """save_trade with sell P&L fields should persist them to JSON."""
        path = save_trade(
            "NVDA", "sell", 5, 120.0, "USD", "2026-02-20",
            sell_price=138.0, realized_pnl=90.0, pnl_rate=0.15,
            hold_days=41, cost_price=120.0,
            base_dir=str(tmp_path),
        )
        data = _read_json(path)
        assert data["sell_price"] == 138.0
        assert data["realized_pnl"] == 90.0
        assert data["pnl_rate"] == pytest.approx(0.15)
        assert data["hold_days"] == 41
        assert data["cost_price"] == 120.0

    def test_save_sell_without_pnl_fields(self, tmp_path):
        """save_trade without P&L fields should not include them in JSON."""
        path = save_trade("NVDA", "sell", 5, 120.0, "USD", "2026-02-20",
                          base_dir=str(tmp_path))
        data = _read_json(path)
        assert "sell_price" not in data
        assert "realized_pnl" not in data
        assert "hold_days" not in data


# ===================================================================
# save_health
# ===================================================================


class TestSaveHealth:
    def test_save_creates_file(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        # KIK-743: HHMMSS 일의화 (같은 날 health 덮어쓰기 방지)
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename.startswith(f"{today}_health_")
        assert filename.endswith(".json")

    def test_save_contains_summary(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["category"] == "health"
        assert data["summary"]["total"] == 2
        assert data["summary"]["healthy"] == 1
        assert data["summary"]["caution"] == 1
        assert data["summary"]["exit"] == 0

    def test_save_contains_positions(self, tmp_path):
        path = save_health(_sample_health_data(), base_dir=str(tmp_path))
        data = _read_json(path)
        assert len(data["positions"]) == 2
        pos0 = data["positions"][0]
        assert pos0["symbol"] == "005930.KS"
        assert pos0["trend"] == "상승"
        assert pos0["quality_label"] == "양호"
        assert pos0["alert_level"] == "none"

    def test_save_creates_health_subdirectory(self, tmp_path):
        save_health({"positions": [], "summary": {}}, base_dir=str(tmp_path))
        assert (tmp_path / "health").is_dir()


# ===================================================================
# load_history
# ===================================================================


class TestLoadHistory:
    def test_load_empty_directory(self, tmp_path):
        result = load_history("screen", base_dir=str(tmp_path))
        assert result == []

    def test_load_nonexistent_directory(self, tmp_path):
        result = load_history("nonexistent", base_dir=str(tmp_path))
        assert result == []

    def test_load_returns_saved_data(self, tmp_path):
        save_screening("value", "kr", _sample_results(), base_dir=str(tmp_path))
        results = load_history("screen", base_dir=str(tmp_path))
        assert len(results) == 1
        assert results[0]["preset"] == "value"
        assert results[0]["region"] == "kr"

    def test_load_with_days_back(self, tmp_path):
        # Save a file for today
        save_screening("value", "kr", [], base_dir=str(tmp_path))

        # Manually create an old file (60 days ago)
        old_date = (date.today() - timedelta(days=60)).isoformat()
        old_dir = tmp_path / "screen"
        old_dir.mkdir(parents=True, exist_ok=True)
        old_file = old_dir / f"{old_date}_kr_old.json"
        with open(old_file, "w") as f:
            json.dump({"date": old_date, "preset": "old", "region": "kr"}, f)

        # days_back=30 should exclude the 60-day old file
        results = load_history("screen", days_back=30, base_dir=str(tmp_path))
        assert len(results) == 1
        assert results[0]["preset"] == "value"

        # days_back=90 should include both
        results_all = load_history("screen", days_back=90, base_dir=str(tmp_path))
        assert len(results_all) == 2

    def test_load_sorts_by_date_desc(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        dates = [
            (date.today() - timedelta(days=2)).isoformat(),
            date.today().isoformat(),
            (date.today() - timedelta(days=1)).isoformat(),
        ]
        for d in dates:
            filepath = screen_dir / f"{d}_kr_value.json"
            with open(filepath, "w") as f:
                json.dump({"date": d, "preset": "value"}, f)

        results = load_history("screen", base_dir=str(tmp_path))
        result_dates = [r["date"] for r in results]
        assert result_dates == sorted(result_dates, reverse=True)

    def test_load_skips_invalid_json(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        # Write a corrupted JSON file
        bad_file = screen_dir / f"{date.today().isoformat()}_bad.json"
        with open(bad_file, "w") as f:
            f.write("{invalid json content")

        # Write a valid file
        save_screening("value", "kr", [], base_dir=str(tmp_path))

        results = load_history("screen", base_dir=str(tmp_path))
        # Only the valid file should be loaded
        assert len(results) == 1
        assert results[0]["preset"] == "value"


# ===================================================================
# list_history_files
# ===================================================================


class TestListHistoryFiles:
    def test_list_empty(self, tmp_path):
        result = list_history_files("screen", base_dir=str(tmp_path))
        assert result == []

    def test_list_returns_paths(self, tmp_path):
        save_screening("value", "kr", [], base_dir=str(tmp_path))
        paths = list_history_files("screen", base_dir=str(tmp_path))
        assert len(paths) == 1
        assert paths[0].endswith(".json")

    def test_list_sorted_desc(self, tmp_path):
        screen_dir = tmp_path / "screen"
        screen_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            d = (date.today() - timedelta(days=i)).isoformat()
            filepath = screen_dir / f"{d}_test.json"
            with open(filepath, "w") as f:
                json.dump({}, f)

        paths = list_history_files("screen", base_dir=str(tmp_path))
        filenames = [Path(p).name for p in paths]
        assert filenames == sorted(filenames, reverse=True)


# ===================================================================
# _safe_filename
# ===================================================================


class TestSafeName:
    def test_dot_replacement(self):
        assert _safe_filename("005930.KS") == "005930_KS"

    def test_slash_replacement(self):
        assert _safe_filename("foo/bar") == "foo_bar"

    def test_special_chars_kospi(self):
        assert _safe_filename("068270.KS") == "068270_KS"

    def test_special_chars_kosdaq(self):
        assert _safe_filename("196170.KQ") == "196170_KQ"

    def test_multiple_dots(self):
        assert _safe_filename("A.B.C") == "A_B_C"

    def test_no_special_chars(self):
        assert _safe_filename("AAPL") == "AAPL"

    def test_mixed_dot_and_slash(self):
        assert _safe_filename("a.b/c.d") == "a_b_c_d"


# ===================================================================
# numpy / NaN / Inf handling
# ===================================================================


class TestNumpyHandling:
    def test_numpy_float(self, tmp_path):
        results = [{"symbol": "X", "value_score": np.float64(72.5), "price": np.float64(100.0)}]
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] == 72.5
        assert isinstance(data["results"][0]["value_score"], float)

    def test_numpy_int(self, tmp_path):
        results = [{"symbol": "X", "value_score": 50, "shares": np.int64(100)}]
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["shares"] == 100
        assert isinstance(data["results"][0]["shares"], int)

    def test_nan_sanitized(self, tmp_path):
        results = [{"symbol": "X", "value_score": float("nan"), "per": np.float64("nan")}]
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] is None
        assert data["results"][0]["per"] is None

    def test_inf_sanitized(self, tmp_path):
        results = [{"symbol": "X", "value_score": float("inf"), "per": np.float64("-inf")}]
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["value_score"] is None
        assert data["results"][0]["per"] is None

    def test_numpy_array_serialized(self, tmp_path):
        results = [{"symbol": "X", "values": np.array([1.0, 2.0, 3.0])}]
        path = save_screening("value", "kr", results, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["results"][0]["values"] == [1.0, 2.0, 3.0]


# ===================================================================
# base_dir parameter
# ===================================================================


# ===================================================================
# save_research (KIK-405)
# ===================================================================


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestSaveResearch:
    def test_stock_research(self, tmp_path):
        result = {
            "type": "stock",
            "symbol": "005930.KS",
            "name": "삼성전자",
            "fundamentals": {"per": 10.5, "pbr": 1.2},
            "value_score": 65.0,
            "grok_research": {"recent_news": "test news"},
            "x_sentiment": {"sentiment_score": 0.5},
            "news": [{"title": "headline"}],
        }
        path = save_research("stock", "005930.KS", result, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["category"] == "research"
        assert data["research_type"] == "stock"
        assert data["target"] == "005930.KS"
        assert data["symbol"] == "005930.KS"
        assert data["name"] == "삼성전자"
        assert data["value_score"] == 65.0
        assert "type" not in data  # "type" from result excluded
        assert data["_saved_at"] is not None

    def test_industry_research(self, tmp_path):
        result = {
            "type": "industry",
            "theme": "반도체",
            "grok_research": {"trends": "AI demand"},
        }
        path = save_research("industry", "반도체", result, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["research_type"] == "industry"
        assert data["target"] == "반도체"
        assert "research" in path

    def test_market_research(self, tmp_path):
        result = {
            "type": "market",
            "market": "KOSPI",
            "macro_indicators": [{"name": "KOSPI", "price": 40000}],
            "grok_research": {"sentiment": "bullish"},
        }
        path = save_research("market", "KOSPI", result, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["research_type"] == "market"
        assert data["macro_indicators"][0]["price"] == 40000

    def test_business_research(self, tmp_path):
        result = {
            "type": "business",
            "symbol": "035420.KS",
            "name": "NAVER",
            "grok_research": {"overview": "imaging company"},
        }
        path = save_research("business", "035420.KS", result, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["research_type"] == "business"
        assert data["target"] == "035420.KS"

    def test_filename_format(self, tmp_path):
        result = {"type": "stock", "symbol": "AAPL"}
        path = save_research("stock", "AAPL", result, base_dir=str(tmp_path))
        fname = Path(path).name
        today = date.today().isoformat()
        assert fname.startswith(today)
        assert "stock_AAPL" in fname

    def test_load_research(self, tmp_path):
        result = {"type": "stock", "symbol": "005930.KS"}
        save_research("stock", "005930.KS", result, base_dir=str(tmp_path))
        loaded = load_history("research", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["research_type"] == "stock"


# ===================================================================
# save_market_context (KIK-405)
# ===================================================================


class TestSaveMarketContext:
    def test_basic(self, tmp_path):
        context = {
            "indices": [
                {"name": "S&P500", "symbol": "^GSPC", "price": 5800},
                {"name": "KOSPI", "symbol": "^KS11", "price": 40000},
                {"name": "VIX", "symbol": "^VIX", "price": 15.0},
                {"name": "USD/KRW", "symbol": "KRW=X", "price": 150.0},
            ]
        }
        path = save_market_context(context, base_dir=str(tmp_path))
        assert Path(path).exists()
        data = _read_json(path)
        assert data["category"] == "market_context"
        assert len(data["indices"]) == 4
        assert data["_saved_at"] is not None

    def test_filename_format(self, tmp_path):
        # KIK-743: HHMMSS 일의화 (같은 날 context 덮어쓰기 방지)
        context = {"indices": []}
        path = save_market_context(context, base_dir=str(tmp_path))
        fname = Path(path).name
        today = date.today().isoformat()
        assert fname.startswith(f"{today}_context_")
        assert fname.endswith(".json")

    def test_load_market_context(self, tmp_path):
        context = {"indices": [{"name": "VIX", "price": 20.0}]}
        save_market_context(context, base_dir=str(tmp_path))
        loaded = load_history("market_context", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["category"] == "market_context"

    def test_numpy_handling(self, tmp_path):
        context = {"indices": [{"name": "test", "price": np.float64(100.5)}]}
        path = save_market_context(context, base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["indices"][0]["price"] == 100.5


# ===================================================================
# base_dir parameter
# ===================================================================


# ===================================================================
# Neo4j dual-write (KIK-399)
# ===================================================================


class TestGraphDualWrite:
    """Verify that save_* functions call graph_store merge functions."""

    @patch("src.data.history.merge_screen", create=True)
    @patch("src.data.history.merge_stock", create=True)
    def test_screening_calls_graph(self, mock_stock, mock_screen, tmp_path):
        with patch.dict("sys.modules", {}):
            save_screening("value", "kr", [{"symbol": "005930.KS", "name": "삼성전자", "sector": "Tech"}], base_dir=str(tmp_path))

    def test_screening_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_stock", side_effect=Exception("Neo4j down")):
            path = save_screening("value", "kr", [{"symbol": "005930.KS"}], base_dir=str(tmp_path))
            assert Path(path).exists()

    def test_report_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_stock", side_effect=Exception("Neo4j down")):
            path = save_report("005930.KS", _sample_stock_data(), 72.5, "저평가", base_dir=str(tmp_path))
            assert Path(path).exists()

    def test_trade_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_stock", side_effect=Exception("Neo4j down")):
            path = save_trade("005930.KS", "buy", 100, 2850, "KRW", "2026-02-17", base_dir=str(tmp_path))
            assert Path(path).exists()

    def test_health_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_health", side_effect=Exception("Neo4j down")):
            path = save_health(_sample_health_data(), base_dir=str(tmp_path))
            assert Path(path).exists()

    def test_research_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_research_full", side_effect=Exception("Neo4j down")):
            result = {"type": "stock", "symbol": "005930.KS", "summary": "test"}
            path = save_research("stock", "005930.KS", result, base_dir=str(tmp_path))
            assert Path(path).exists()

    @patch("src.data.graph_store.link_research_supersedes")
    @patch("src.data.graph_store.merge_research_full")
    @patch("src.data.graph_store.merge_stock")
    @patch("src.data.graph_store.is_available", return_value=True)
    def test_research_passes_sector_to_merge_stock(
        self, mock_avail, mock_merge_stock, mock_merge_research, mock_link, tmp_path,
    ):
        """KIK-490: save_research should pass sector from fundamentals to merge_stock."""
        result = {
            "type": "stock",
            "symbol": "005930.KS",
            "name": "삼성전자",
            "fundamentals": {"sector": "Technology", "per": 10.5},
            "summary": "test",
        }
        save_research("stock", "005930.KS", result, base_dir=str(tmp_path))
        mock_merge_stock.assert_called_once_with(
            symbol="005930.KS", name="삼성전자", sector="Technology",
        )

    @patch("src.data.graph_store.link_research_supersedes")
    @patch("src.data.graph_store.merge_research_full")
    @patch("src.data.graph_store.merge_stock")
    @patch("src.data.graph_store.is_available", return_value=True)
    def test_research_no_fundamentals_passes_empty_sector(
        self, mock_avail, mock_merge_stock, mock_merge_research, mock_link, tmp_path,
    ):
        """KIK-490: business research without fundamentals passes empty sector."""
        result = {
            "type": "business",
            "symbol": "035420.KS",
            "name": "NAVER",
            "grok_research": {"overview": "imaging"},
        }
        save_research("business", "035420.KS", result, base_dir=str(tmp_path))
        mock_merge_stock.assert_called_once_with(
            symbol="035420.KS", name="NAVER", sector="",
        )

    @patch("src.data.graph_store.tag_theme")
    @patch("src.data.graph_store.merge_screen")
    @patch("src.data.graph_store.merge_stock")
    def test_screening_with_theme_calls_tag_theme(self, mock_stock, mock_screen, mock_tag, tmp_path):
        """KIK-487: save_screening with theme should call tag_theme for each symbol."""
        save_screening(
            "value", "kr",
            [{"symbol": "005930.KS", "name": "삼성전자", "sector": "Tech"},
             {"symbol": "000660.KS", "name": "SK하이닉스", "sector": "Tech"}],
            theme="ai",
            base_dir=str(tmp_path),
        )
        assert mock_tag.call_count == 2
        mock_tag.assert_any_call("005930.KS", "ai")
        mock_tag.assert_any_call("000660.KS", "ai")

    @patch("src.data.graph_store.tag_theme")
    @patch("src.data.graph_store.merge_screen")
    @patch("src.data.graph_store.merge_stock")
    def test_screening_without_theme_skips_tag(self, mock_stock, mock_screen, mock_tag, tmp_path):
        """KIK-487: save_screening without theme should not call tag_theme."""
        save_screening(
            "value", "kr",
            [{"symbol": "005930.KS", "name": "삼성전자"}],
            base_dir=str(tmp_path),
        )
        mock_tag.assert_not_called()

    def test_market_context_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_market_context_full", side_effect=Exception("Neo4j down")):
            context = {"indices": [{"name": "VIX", "price": 20.0}]}
            path = save_market_context(context, base_dir=str(tmp_path))
            assert Path(path).exists()


# ===================================================================
# save_stress_test (KIK-428)
# ===================================================================


class TestSaveStressTest:
    def test_save_creates_file(self, tmp_path):
        path = save_stress_test(
            scenario="트리플 약세",
            symbols=["005930.KS", "AAPL"],
            portfolio_impact=-0.15,
            base_dir=str(tmp_path),
        )
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        path = save_stress_test(
            scenario="트리플 약세",
            symbols=["005930.KS"],
            portfolio_impact=-0.10,
            base_dir=str(tmp_path),
        )
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename.startswith(today)
        assert filename.endswith(".json")

    def test_save_contains_metadata(self, tmp_path):
        path = save_stress_test(
            scenario="달러 강세·원화 약세",
            symbols=["005930.KS", "AAPL", "247540.KQ"],
            portfolio_impact=0.05,
            var_result={"var_95_daily": 0.02, "var_99_daily": 0.03},
            concentration={"sector_hhi": 0.3},
            recommendations=["헤지 추가"],
            base_dir=str(tmp_path),
        )
        data = _read_json(path)
        assert data["category"] == "stress_test"
        assert data["scenario"] == "달러 강세·원화 약세"
        assert data["symbols"] == ["005930.KS", "AAPL", "247540.KQ"]
        assert data["portfolio_impact"] == 0.05
        assert data["var_result"]["var_95_daily"] == 0.02
        assert data["concentration"]["sector_hhi"] == 0.3
        assert data["recommendations"] == ["헤지 추가"]
        assert "_saved_at" in data

    def test_save_creates_stress_test_subdirectory(self, tmp_path):
        save_stress_test(
            scenario="테스트", symbols=[], portfolio_impact=0,
            base_dir=str(tmp_path),
        )
        assert (tmp_path / "stress_test").is_dir()

    def test_load_stress_test(self, tmp_path):
        save_stress_test(
            scenario="트리플 약세", symbols=["005930.KS"],
            portfolio_impact=-0.15, base_dir=str(tmp_path),
        )
        loaded = load_history("stress_test", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["category"] == "stress_test"
        assert loaded[0]["scenario"] == "트리플 약세"

    def test_numpy_handling(self, tmp_path):
        path = save_stress_test(
            scenario="테스트",
            symbols=["X"],
            portfolio_impact=np.float64(-0.123),
            var_result={"var_95_daily": np.float64(0.05)},
            base_dir=str(tmp_path),
        )
        data = _read_json(path)
        assert isinstance(data["portfolio_impact"], float)
        assert data["var_result"]["var_95_daily"] == 0.05

    def test_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_stock", side_effect=Exception("Neo4j down")):
            path = save_stress_test(
                scenario="트리플 약세", symbols=["005930.KS"],
                portfolio_impact=-0.15, base_dir=str(tmp_path),
            )
            assert Path(path).exists()


# ===================================================================
# save_forecast (KIK-428)
# ===================================================================


class TestSaveForecast:
    def _sample_positions(self):
        return [
            {"symbol": "005930.KS", "optimistic": 0.30, "base": 0.15, "pessimistic": -0.05, "method": "analyst"},
            {"symbol": "AAPL", "optimistic": 0.25, "base": 0.10, "pessimistic": -0.10, "method": "analyst"},
        ]

    def test_save_creates_file(self, tmp_path):
        path = save_forecast(
            positions=self._sample_positions(),
            total_value_krw=5000000,
            base_dir=str(tmp_path),
        )
        assert Path(path).exists()

    def test_save_file_naming(self, tmp_path):
        # KIK-744: HHMMSSffffff + uuid hex 로 완전 일의화
        path = save_forecast(
            positions=self._sample_positions(),
            base_dir=str(tmp_path),
        )
        filename = Path(path).name
        today = date.today().isoformat()
        assert filename.startswith(f"{today}_forecast_")
        assert filename.endswith(".json")

    def test_save_contains_metadata(self, tmp_path):
        positions = self._sample_positions()
        path = save_forecast(
            positions=positions,
            total_value_krw=7500000,
            base_dir=str(tmp_path),
        )
        data = _read_json(path)
        assert data["category"] == "forecast"
        assert data["total_value_krw"] == 7500000
        assert "portfolio" in data
        assert "positions" in data
        assert len(data["positions"]) == 2
        assert "_saved_at" in data

    def test_save_computes_portfolio_averages(self, tmp_path):
        positions = self._sample_positions()
        path = save_forecast(positions=positions, base_dir=str(tmp_path))
        data = _read_json(path)
        pf = data["portfolio"]
        # Average of [0.30, 0.25] = 0.275, [0.15, 0.10] = 0.125, [-0.05, -0.10] = -0.075
        assert abs(pf["optimistic"] - 0.275) < 0.001
        assert abs(pf["base"] - 0.125) < 0.001
        assert abs(pf["pessimistic"] - (-0.075)) < 0.001

    def test_save_creates_forecast_subdirectory(self, tmp_path):
        save_forecast(positions=[], base_dir=str(tmp_path))
        assert (tmp_path / "forecast").is_dir()

    def test_load_forecast(self, tmp_path):
        save_forecast(
            positions=self._sample_positions(),
            total_value_krw=5000000,
            base_dir=str(tmp_path),
        )
        loaded = load_history("forecast", base_dir=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0]["category"] == "forecast"

    def test_empty_positions(self, tmp_path):
        path = save_forecast(positions=[], base_dir=str(tmp_path))
        data = _read_json(path)
        assert data["portfolio"]["optimistic"] == 0
        assert data["portfolio"]["base"] == 0
        assert data["portfolio"]["pessimistic"] == 0

    def test_graph_failure_still_saves(self, tmp_path):
        with patch("src.data.graph_store.merge_stock", side_effect=Exception("Neo4j down")):
            path = save_forecast(
                positions=self._sample_positions(),
                total_value_krw=5000000,
                base_dir=str(tmp_path),
            )
            assert Path(path).exists()


class TestBaseDirParameter:
    def test_deep_base_dir(self, tmp_path):
        deep_dir = str(tmp_path / "a" / "b" / "c")
        path = save_screening("value", "kr", [], base_dir=deep_dir)
        assert Path(path).exists()
        assert "a/b/c/screen" in path or "a\\b\\c\\screen" in path
