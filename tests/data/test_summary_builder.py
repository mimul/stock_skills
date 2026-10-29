"""Tests for src/data/summary_builder.py (KIK-420).

Verifies template-based summary generation for each node type.
"""

import pytest

from src.data.context.summary_builder import (
    _trunc,
    build_screen_summary,
    build_report_summary,
    build_trade_summary,
    build_health_summary,
    build_research_summary,
    build_market_context_summary,
    build_note_summary,
)


# ===================================================================
# _trunc
# ===================================================================


class TestTrunc:
    def test_short_text_unchanged(self):
        assert _trunc("hello", 200) == "hello"

    def test_long_text_truncated(self):
        result = _trunc("a" * 250, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty_text(self):
        assert _trunc("", 200) == ""

    def test_none_text(self):
        assert _trunc(None, 200) == ""


# ===================================================================
# build_screen_summary
# ===================================================================


class TestBuildScreenSummary:
    def test_full_summary(self):
        result = build_screen_summary("2026-02-18", "alpha", "kr",
                                      ["005930.KS", "015760.KS"])
        assert "kr" in result
        assert "alpha" in result
        assert "2026-02-18" in result
        assert "005930.KS" in result

    def test_no_symbols(self):
        result = build_screen_summary("2026-02-18", "value", "us")
        assert "us" in result
        assert "Top:" not in result

    def test_empty_inputs(self):
        result = build_screen_summary("", "", "")
        assert isinstance(result, str)

    def test_max_5_symbols(self):
        symbols = [
            "005930.KS", "000660.KS", "035420.KS", "105560.KS", "247540.KQ",
            "069500.KS", "005380.KS", "068270.KS", "196170.KQ",
        ]
        result = build_screen_summary("2026-01-01", "alpha", "kr", symbols)
        # Should only include first 5
        assert "247540.KQ" in result
        assert "069500.KS" not in result

    def test_max_length(self):
        assert len(build_screen_summary("2026-02-18", "alpha", "kr",
                                         ["A" * 50] * 5)) <= 200


# ===================================================================
# build_report_summary
# ===================================================================


class TestBuildReportSummary:
    def test_full_summary(self):
        result = build_report_summary("005930.KS", "삼성전자", 54.8,
                                      "slightly undervalued", "Technology")
        assert "005930.KS" in result
        assert "삼성전자" in result
        assert "54.8" in result

    def test_minimal(self):
        result = build_report_summary("AAPL")
        assert "AAPL" in result

    def test_no_score(self):
        result = build_report_summary("005930.KS", verdict="fair")
        assert "fair" in result


# ===================================================================
# build_trade_summary
# ===================================================================


class TestBuildTradeSummary:
    def test_buy(self):
        result = build_trade_summary("2026-02-17", "buy", "005930.KS", 100,
                                     "initial purchase")
        assert "BUY" in result
        assert "005930.KS" in result
        assert "100" in result

    def test_sell(self):
        result = build_trade_summary("2026-02-17", "sell", "AAPL", 5)
        assert "SELL" in result
        assert "AAPL" in result

    def test_empty_trade_type(self):
        result = build_trade_summary("2026-01-01", "", "XYZ", 0)
        assert "TRADE" in result

    def test_max_length(self):
        result = build_trade_summary("2026-01-01", "buy", "005930.KS", 100,
                                     "a" * 300)
        assert len(result) <= 200


# ===================================================================
# build_health_summary
# ===================================================================


class TestBuildHealthSummary:
    def test_full_summary(self):
        summary = {"total": 5, "healthy": 3, "early_warning": 1, "exit": 1}
        result = build_health_summary("2026-02-18", summary)
        assert "헬스체크" in result
        assert "전체 5종목" in result
        assert "건전3" in result
        assert "EXIT1" in result

    def test_none_summary(self):
        result = build_health_summary("2026-02-18", None)
        assert "헬스체크" in result

    def test_empty_summary(self):
        result = build_health_summary("2026-02-18", {})
        assert "헬스체크" in result


# ===================================================================
# build_research_summary
# ===================================================================


class TestBuildResearchSummary:
    def test_stock_with_news(self):
        result_data = {
            "name": "삼성전자",
            "news": [{"title": "삼성전자 실적 서프라이즈"}],
        }
        result = build_research_summary("stock", "005930.KS", result_data)
        assert "삼성전자" in result

    def test_stock_with_grok(self):
        result_data = {
            "grok_research": {
                "recent_news": ["Big news headline"],
                "x_sentiment": {"score": 7.5},
            },
        }
        result = build_research_summary("stock", "AAPL", result_data)
        assert "Big news" in result

    def test_market_type(self):
        result_data = {
            "grok_research": {
                "price_action": "Bullish trend continues",
            },
        }
        result = build_research_summary("market", "KOSPI", result_data)
        assert "Bullish" in result

    def test_industry_type(self):
        result_data = {
            "grok_research": {"trends": "AI demand surging"},
        }
        result = build_research_summary("industry", "반도체", result_data)
        assert "AI demand" in result

    def test_business_type(self):
        result_data = {
            "name": "NAVER",
            "grok_research": {"overview": "검색 포털과 커머스 플랫폼 운영"},
        }
        result = build_research_summary("business", "035420.KS", result_data)
        assert "NAVER" in result

    def test_empty_result(self):
        result = build_research_summary("stock", "XYZ", {})
        assert isinstance(result, str)

    def test_max_length(self):
        result_data = {
            "grok_research": {"recent_news": ["x" * 300]},
        }
        result = build_research_summary("stock", "XYZ", result_data)
        assert len(result) <= 200


# ===================================================================
# build_market_context_summary
# ===================================================================


class TestBuildMarketContextSummary:
    def test_with_indices(self):
        indices = [
            {"name": "S&P500", "price": 5800},
            {"name": "KOSPI", "price": 2650},
        ]
        result = build_market_context_summary("2026-02-18", indices)
        assert "2026-02-18" in result
        assert "S&P500" in result

    def test_no_indices(self):
        result = build_market_context_summary("2026-02-18")
        assert "2026-02-18" in result

    def test_with_grok_rotation(self):
        grok = {"sector_rotation": ["Tech to Value"]}
        result = build_market_context_summary("2026-02-18",
                                               grok_research=grok)
        assert "Tech to Value" in result

    def test_max_3_indices(self):
        indices = [{"name": f"IDX{i}", "price": i * 100} for i in range(1, 10)]
        result = build_market_context_summary("2026-02-18", indices)
        # Only first 3 should be included
        assert "IDX1" in result
        assert "IDX3" in result
        assert "IDX4" not in result


# ===================================================================
# build_note_summary
# ===================================================================


class TestBuildNoteSummary:
    def test_full_note(self):
        result = build_note_summary("005930.KS", "thesis", "EV growth")
        assert "005930.KS" in result
        assert "thesis:" in result
        assert "EV growth" in result

    def test_no_symbol(self):
        result = build_note_summary("", "lesson", "Sold too late")
        assert "lesson:" in result
        assert "Sold too late" in result

    def test_empty(self):
        result = build_note_summary()
        assert result == ""

    def test_max_length(self):
        result = build_note_summary("SYM", "thesis", "x" * 300)
        assert len(result) <= 200

    # KIK-429: category support
    def test_category_portfolio_no_symbol(self):
        result = build_note_summary("", "review", "PF check", category="portfolio")
        assert "[portfolio]" in result
        assert "review:" in result

    def test_category_stock_with_symbol(self):
        result = build_note_summary("005930.KS", "thesis", "test", category="stock")
        assert "005930.KS" in result
        assert "[stock]" not in result

    # KIK-534: lesson with trigger/expected_action
    def test_lesson_with_trigger_and_expected_action(self):
        result = build_note_summary(
            "005930.KS", "lesson", "고점 매수했다",
            trigger="RSI70 초과에서 매수", expected_action="RSI70 초과에서는 매수 안 함",
        )
        assert "투자 lesson:" in result
        assert "RSI70 초과에서 매수" in result
        assert "→" in result
        assert "RSI70 초과에서는 매수 안 함" in result
        assert "005930.KS" in result

    def test_lesson_with_trigger_only(self):
        result = build_note_summary(
            "", "lesson", "content",
            trigger="모멘텀에 추격 매수했다",
        )
        assert "투자 lesson:" in result
        assert "모멘텀에 추격 매수했다" in result

    def test_lesson_with_expected_action_only(self):
        result = build_note_summary(
            "", "lesson", "",
            expected_action="거래량 확인 후 진입",
        )
        assert "투자 lesson:" in result
        assert "→ 거래량 확인 후 진입" in result

    def test_lesson_without_extra_fields_is_normal(self):
        """trigger/expected_action 없는 lesson 은 기존 형식."""
        result = build_note_summary("AAPL", "lesson", "Don't chase")
        assert "lesson:" in result
        assert "Don't chase" in result
        assert "투자 lesson:" not in result

    def test_lesson_with_category(self):
        result = build_note_summary(
            "", "lesson", "Portfolio lesson",
            category="portfolio",
            trigger="PF 쏠림 방치", expected_action="월간 리밸런싱",
        )
        assert "[portfolio]" in result
        assert "투자 lesson:" in result
        assert "PF 쏠림 방치" in result
