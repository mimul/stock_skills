"""grok_context.py 테스트 — 압축 지식 컨텍스트 추출 (KIK-488).

검증 범위:
- get_stock_context: 보유/비보유, 전체 이력, 빈 이력, graceful degradation
- get_industry_context: 섹터 내 보유 종목, 과거 리서치
- get_market_context: 보유 섹터, 최근 시장 컨텍스트
- get_business_context: 보유 여부, 과거 리서치, 투자 논거
- _truncate_context: 줄 단위 절단
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.context.grok_context import (
    _truncate_context,
    get_stock_context,
    get_industry_context,
    get_market_context,
    get_business_context,
)


# ---------------------------------------------------------------------------
# _truncate_context
# ---------------------------------------------------------------------------


class TestTruncateContext:

    def test_empty_string(self):
        assert _truncate_context("") == ""

    def test_short_text_unchanged(self):
        text = "Short text"
        assert _truncate_context(text) == text

    def test_truncates_long_text(self):
        # max_tokens=10 → max_chars=30
        lines = ["Line 1 - 15 chars", "Line 2 - 15 chars", "Line 3 - 15 chars"]
        text = "\n".join(lines)
        result = _truncate_context(text, max_tokens=10)
        # Only first line should fit within 30 chars
        assert "Line 1" in result
        assert "Line 3" not in result

    def test_truncates_at_line_boundary(self):
        # max_tokens=20 → max_chars=60
        lines = ["AAAA " * 10, "BBBB " * 10]  # Each ~50 chars
        text = "\n".join(lines)
        result = _truncate_context(text, max_tokens=20)
        # First line is 50 chars, fits in 60
        assert "AAAA" in result
        # Second line would push over, should be excluded
        assert "BBBB" not in result


# ---------------------------------------------------------------------------
# get_stock_context
# ---------------------------------------------------------------------------

def _make_stock_history(
    trades=None, reports=None, notes=None,
    screens=None, researches=None, health_checks=None, themes=None,
):
    """테스트용 이력 dict 를 만든다."""
    return {
        "trades": trades or [],
        "reports": reports or [],
        "notes": notes or [],
        "screens": screens or [],
        "researches": researches or [],
        "health_checks": health_checks or [],
        "themes": themes or [],
    }


class TestGetStockContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_neo4j_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = None
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_empty_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history()
        mock_gs.is_held.return_value = False
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_held_stock_with_full_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "buy", "date": "2026-02-14", "shares": 400, "price": 166.31}],
            reports=[{"date": "2026-02-21", "score": 52.65, "verdict": "다소 저평가"}],
            notes=[
                {"type": "thesis", "content": "국내 완성차 대표주. 성장성과 저평가를 겸비."},
                {"type": "concern", "content": "차트상 헤드앤숄더 완성 가능성"},
            ],
            screens=[
                {"preset": "alpha"}, {"preset": "value"}, {"preset": "long-term"},
                {"preset": "alpha"}, {"preset": "value"},
            ],
            researches=[{"date": "2026-02-20", "summary": "북미 수요 견조, 실적 확대 중"}],
            health_checks=[{"date": "2026-02-24"}],
            themes=["Automotive", "Korea"],
        )

        result = get_stock_context("005380.KS")
        assert "[INVESTOR CONTEXT]" in result
        assert "Currently held" in result
        assert "400 shares" in result
        assert "52.65" in result
        assert "Thesis:" in result
        assert "Concern:" in result
        assert "Appeared 5 times" in result
        assert "북미 수요 견조" in result
        assert "Last health check: 2026-02-24" in result
        assert "Themes:" in result
        assert "Focus your research" in result

    @patch("src.data.graph_store", create=True)
    def test_non_held_stock_with_sell(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = False
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "sell", "date": "2026-02-25"}],
            reports=[{"date": "2026-02-20", "score": 45.0, "verdict": "저평가"}],
        )

        result = get_stock_context("105560.KS")
        assert "Previously held" in result
        assert "sold 2026-02-25" in result

    @patch("src.data.graph_store", create=True)
    def test_notes_limited_to_two(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "buy", "date": "2026-01-01", "shares": 10, "price": 100}],
            notes=[
                {"type": "thesis", "content": "Thesis 1"},
                {"type": "concern", "content": "Concern 1"},
                {"type": "thesis", "content": "Thesis 2 should be excluded"},
            ],
        )

        result = get_stock_context("TEST")
        assert "Thesis 1" in result
        assert "Concern 1" in result
        assert "Thesis 2" not in result

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation_on_import_error(self, mock_gs):
        """graph_store.is_available 이 예외를 던지면 "" 를 반환한다.

        가장 바깥 try/except 가 모든 오류(graph_store 미사용 시 ImportError 포함)를
        잡는지 검증한다.
        """
        mock_gs.is_available.side_effect = ImportError("no graph_store")
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation_on_exception(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("Connection failed")
        assert get_stock_context("NVDA") == ""


# ---------------------------------------------------------------------------
# get_industry_context
# ---------------------------------------------------------------------------


class TestGetIndustryContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_industry_context("semiconductor") == ""

    @patch("src.data.graph_store", create=True)
    def test_with_held_stocks_in_sector(self, mock_gs):
        mock_gs.is_available.return_value = True

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = [{"symbol": "NVDA"}, {"symbol": "AVGO"}]
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_industry_context("semiconductor")
        assert "NVDA" in result
        assert "AVGO" in result
        assert "Focus on developments" in result

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_data(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = []
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_industry_context("semiconductor")
        assert result == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_industry_context("semiconductor") == ""


# ---------------------------------------------------------------------------
# get_market_context
# ---------------------------------------------------------------------------


class TestGetMarketContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_market_context() == ""

    @patch("src.data.graph_store", create=True)
    def test_with_held_sectors(self, mock_gs):
        mock_gs.is_available.return_value = True

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = [
            {"sector": "Technology", "cnt": 3},
            {"sector": "Financial", "cnt": 2},
        ]
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_market_context()
        assert "Technology(3)" in result
        assert "Financial(2)" in result
        assert "Focus on how current market" in result

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_market_context() == ""


# ---------------------------------------------------------------------------
# get_business_context
# ---------------------------------------------------------------------------


class TestGetBusinessContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = None
        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_held_stock_with_research_and_thesis(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            researches=[
                {"date": "2026-02-20", "summary": "Strong platform business", "research_type": "business"},
            ],
            themes=["Tech", "Cloud"],
            notes=[{"type": "thesis", "content": "Cloud growth accelerating"}],
        )

        result = get_business_context("AAPL")
        assert "[INVESTOR CONTEXT]" in result
        assert "Currently held" in result
        assert "Strong platform business" in result
        assert "Tech" in result
        assert "Cloud growth accelerating" in result
        assert "Focus on how the business model" in result

    @patch("src.data.graph_store", create=True)
    def test_empty_history_returns_empty(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = False
        mock_gs.get_stock_history.return_value = _make_stock_history()

        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_business_context("AAPL") == ""
