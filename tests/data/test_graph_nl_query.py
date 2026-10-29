"""src.data.graph_query.nl_query 모듈 테스트 (KIK-409).

graph_query 함수는 모두 모킹한다 — Neo4j 의존 없음.
"""

from unittest.mock import patch

import pytest

from src.data.graph_query.nl_query import (
    query,
    format_result,
    _extract_symbol,
    _extract_symbol_and_type,
)


# ===================================================================
# 심볼 추출 테스트
# ===================================================================

class TestExtractSymbol:
    def test_kr_ticker(self):
        """6자리 코스피 종목코드를 통째로 추출한다."""
        assert _extract_symbol("005930.KS 지난 리포트") == "005930.KS"

    def test_us_ticker(self):
        assert _extract_symbol("AAPL 거래 이력") == "AAPL"

    def test_kq_ticker(self):
        """코스닥(.KQ) 종목코드도 통째로 추출한다."""
        assert _extract_symbol("247540.KQ 정보") == "247540.KQ"

    def test_no_symbol(self):
        assert _extract_symbol("반복 후보") is None

    def test_symbol_and_type_stock(self):
        result = _extract_symbol_and_type("005930.KS 리서치 이력")
        assert result == {"symbol": "005930.KS", "research_type": "stock"}

    def test_symbol_and_type_industry(self):
        result = _extract_symbol_and_type("반도체 업계 리서치")
        assert result["research_type"] == "industry"

    def test_symbol_and_type_market(self):
        result = _extract_symbol_and_type("시장 리서치")
        assert result["research_type"] == "market"


# ===================================================================
# 템플릿 매칭 + 디스패치 테스트
# ===================================================================

class TestQuery:
    @patch("src.data.graph_query.nl_query.graph_query")
    def test_prior_report_match(self, mock_gq):
        mock_gq.get_prior_report.return_value = {
            "date": "2026-02-17", "score": 75, "verdict": "저평가",
        }
        result = query("005930.KS 지난 리포트는?")
        assert result is not None
        assert result["query_type"] == "prior_report"
        assert "저평가" in result["formatted"]
        mock_gq.get_prior_report.assert_called_once_with("005930.KS")

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_prior_report_not_found(self, mock_gq):
        mock_gq.get_prior_report.return_value = None
        result = query("005930.KS 이전 리포트")
        assert result is None

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_recurring_picks_match(self, mock_gq):
        mock_gq.get_recurring_picks.return_value = [
            {"symbol": "005930.KS", "count": 5, "last_date": "2026-02-15"},
            {"symbol": "AAPL", "count": 3, "last_date": "2026-02-10"},
        ]
        result = query("반복 후보에 오른 종목은?")
        assert result is not None
        assert result["query_type"] == "recurring_picks"
        assert "005930.KS" in result["formatted"]
        assert "5" in result["formatted"]

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_recurring_picks_often_appears(self, mock_gq):
        """'자주 나오는' 패턴도 매칭되어야 한다."""
        mock_gq.get_recurring_picks.return_value = [
            {"symbol": "AAPL", "count": 2, "last_date": "2026-02-01"},
        ]
        result = query("자주 나오는데 안 산 종목")
        assert result is not None
        assert result["query_type"] == "recurring_picks"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_research_chain_match(self, mock_gq):
        mock_gq.get_research_chain.return_value = [
            {"date": "2026-02-17", "summary": "HBM market growing"},
        ]
        result = query("005930.KS 리서치 이력")
        assert result is not None
        assert result["query_type"] == "research_chain"
        assert "HBM market growing" in result["formatted"]

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_market_context_match(self, mock_gq):
        mock_gq.get_recent_market_context.return_value = {
            "date": "2026-02-17",
            "indices": [{"name": "KOSPI", "value": "3200"}],
        }
        result = query("최근 시황은?")
        assert result is not None
        assert result["query_type"] == "market_context"
        assert "KOSPI" in result["formatted"]

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_trade_context_match(self, mock_gq):
        mock_gq.get_trade_context.return_value = {
            "trades": [{"date": "2026-01-15", "type": "buy", "shares": 100, "price": 2850}],
            "notes": [{"date": "2026-01-15", "type": "thesis", "content": "HBM growth"}],
        }
        result = query("005930.KS 거래 이력")
        assert result is not None
        assert result["query_type"] == "trade_context"
        assert "2850" in result["formatted"]
        assert "HBM growth" in result["formatted"]

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_notes_match(self, mock_gq):
        mock_gq.get_trade_context.return_value = {
            "trades": [],
            "notes": [{"date": "2026-02-17", "type": "thesis", "content": "Strong fundamentals"}],
        }
        result = query("005930.KS 투자 메모")
        assert result is not None
        assert result["query_type"] == "notes"

    def test_no_match(self):
        result = query("오늘 날씨는?")
        assert result is None

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_no_symbol_for_report(self, mock_gq):
        """종목 없는 리포트 조회는 None 을 반환해야 한다."""
        result = query("지난 리포트")
        assert result is None


# ===================================================================
# 포매터 테스트
# ===================================================================

class TestFormatResult:
    def test_fmt_prior_report_empty(self):
        result = format_result("prior_report", None, {"symbol": "005930.KS"})
        assert "찾을 수 없습니다" in result

    def test_fmt_recurring_picks_empty(self):
        result = format_result("recurring_picks", [], {})
        assert "없습니다" in result

    def test_fmt_research_chain_empty(self):
        result = format_result("research_chain", [], {"symbol": "AAPL", "research_type": "stock"})
        assert "찾을 수 없습니다" in result

    def test_fmt_market_context_empty(self):
        result = format_result("market_context", None, {})
        assert "찾을 수 없습니다" in result

    def test_fmt_trade_context_empty(self):
        result = format_result("trade_context", {"trades": [], "notes": []}, {"symbol": "005930.KS"})
        assert "찾을 수 없습니다" in result


# ===================================================================
# 템플릿 우선순위·오매칭 방지 (코드 리뷰 M1)
# ===================================================================

class TestTemplatePrecedence:
    @patch("src.data.graph_query.nl_query.graph_query")
    def test_last_stress_test_goes_to_stress_history(self, mock_gq):
        mock_gq.get_stress_test_history.return_value = []
        result = query("지난번 스트레스 테스트 결과 보여줘")
        assert result is not None
        assert result["query_type"] == "stress_test_history"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_last_forecast_goes_to_forecast_history(self, mock_gq):
        mock_gq.get_forecast_history.return_value = []
        result = query("지난번 포캐스트 추이")
        assert result is not None
        assert result["query_type"] == "forecast_history"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_last_report_still_prior_report(self, mock_gq):
        mock_gq.get_prior_report.return_value = {"date": "2026-01-01", "score": 70, "verdict": "중립"}
        result = query("005930.KS 지난번 리포트")
        assert result["query_type"] == "prior_report"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_asset_allocation_reason_is_not_trade_context(self, mock_gq):
        mock_gq.get_trade_context.return_value = None
        result = query("자산 배분을 바꾼 이유")
        assert result is None or result["query_type"] != "trade_context"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_buy_reason_is_trade_context(self, mock_gq):
        mock_gq.get_trade_context.return_value = None
        query("005930.KS 산 이유가 뭐였지")
        mock_gq.get_trade_context.assert_called_once()

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_raw_material_is_not_catalyst(self, mock_gq):
        mock_gq.get_catalysts.return_value = None
        result = query("005930.KS 원재료 가격 영향")
        assert result is None or result["query_type"] != "catalysts"

    @patch("src.data.graph_query.nl_query.graph_query")
    def test_certain_ratio_is_not_upcoming_events(self, mock_gq):
        mock_gq.get_upcoming_events.return_value = None
        result = query("일정 비율 이상 현금 유지")
        assert result is None or result["query_type"] != "upcoming_events"
