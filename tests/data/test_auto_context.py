"""Tests for src.data.auto_context module (KIK-411/420/427).

All graph_store/graph_query functions are mocked — no Neo4j dependency.
KIK-420 additions: vector search integration tests.
KIK-427 additions: freshness label tests.
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.data.context.auto_context import (
    _action_directive,
    _best_freshness,
    _check_bookmarked,
    _days_since,
    _extract_symbol,
    _format_context,
    _format_lesson_section,
    _format_market_context,
    _format_vector_results,
    _fresh_hours,
    _has_bought_not_sold,
    _has_concern_notes,
    _has_exit_alert,
    _has_recent_research,
    _hours_since,
    _infer_skill_from_vectors,
    _is_market_query,
    _is_portfolio_query,
    _load_lessons,
    _merge_context,
    _recent_hours,
    _recommend_skill,
    _resolve_symbol,
    _screening_count,
    _thesis_needs_review,
    _vector_search,
    freshness_action,
    freshness_label,
    get_context,
)


# ===================================================================
# Symbol extraction tests
# ===================================================================

class TestExtractSymbol:
    def test_kospi_ticker(self):
        assert _extract_symbol("005930.KS 어때?") == "005930.KS"

    def test_kosdaq_ticker(self):
        assert _extract_symbol("247540.KQ 상황은?") == "247540.KQ"

    def test_us_ticker(self):
        assert _extract_symbol("AAPL 조사해줘") == "AAPL"

    def test_kr_code_not_truncated(self):
        """6자리 종목코드가 앞자리 0 포함 통째로 매칭되어야 한다."""
        assert _extract_symbol("000660.KS 분석") == "000660.KS"

    def test_no_symbol(self):
        assert _extract_symbol("삼성전자 상황은?") is None

    def test_unsupported_suffix_not_recognized(self):
        """지원하지 않는 접미사(.T/.SI)는 심볼로 인식하지 않는다."""
        assert _extract_symbol("7203.T 어때?") is None
        assert _extract_symbol("D05.SI 상황은?") is None

    def test_embedded_in_sentence(self):
        assert _extract_symbol("최근 005930.KS는 어떻게 되고 있어?") == "005930.KS"


# ===================================================================
# Keyword detection tests
# ===================================================================

class TestKeywordDetection:
    def test_market_query_kr(self):
        assert _is_market_query("오늘 시황은?") is True

    def test_market_query_en(self):
        assert _is_market_query("market overview") is True

    def test_market_query_negative(self):
        assert _is_market_query("삼성전자 어때?") is False

    def test_market_share_is_not_market_query(self):
        """"시장 점유율"·"시장가"는 종목 질문이다 (코드 리뷰 H2)."""
        assert _is_market_query("005930.KS 시장 점유율 어때?") is False
        assert _is_market_query("삼성전자 시장가 매수") is False

    def test_market_query_variants(self):
        assert _is_market_query("요즘 장세 어때?") is True
        assert _is_market_query("증시 분위기") is True

    def test_portfolio_query_kr(self):
        assert _is_portfolio_query("포트폴리오 괜찮아?") is True

    def test_portfolio_query_short(self):
        assert _is_portfolio_query("PF 확인해줘") is True

    def test_portfolio_query_negative(self):
        assert _is_portfolio_query("AAPL 조사해줘") is False


# ===================================================================
# Graph state analysis helpers
# ===================================================================

class TestDaysSince:
    def test_today(self):
        assert _days_since(date.today().isoformat()) == 0

    def test_yesterday(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert _days_since(yesterday) == 1

    def test_invalid_date(self):
        assert _days_since("not-a-date") == 9999

    def test_none(self):
        assert _days_since(None) == 9999


class TestHasBoughtNotSold:
    def test_bought_only(self):
        history = {"trades": [{"type": "buy", "shares": 100}]}
        assert _has_bought_not_sold(history) is True

    def test_bought_and_sold_equal(self):
        history = {"trades": [
            {"type": "buy", "shares": 100},
            {"type": "sell", "shares": 100},
        ]}
        assert _has_bought_not_sold(history) is False

    def test_no_trades(self):
        assert _has_bought_not_sold({}) is False
        assert _has_bought_not_sold({"trades": []}) is False

    def test_multiple_buys_partial_sell(self):
        history = {"trades": [
            {"type": "buy", "shares": 100},
            {"type": "buy", "shares": 200},
            {"type": "sell", "shares": 100},
        ]}
        assert _has_bought_not_sold(history) is True


class TestScreeningCount:
    def test_zero(self):
        assert _screening_count({}) == 0
        assert _screening_count({"screens": []}) == 0

    def test_multiple(self):
        history = {"screens": [
            {"date": "2026-01-01"},
            {"date": "2026-01-15"},
            {"date": "2026-02-01"},
        ]}
        assert _screening_count(history) == 3


class TestHasRecentResearch:
    def test_recent(self):
        today = date.today().isoformat()
        history = {"researches": [{"date": today, "research_type": "stock"}]}
        assert _has_recent_research(history, 7) is True

    def test_old(self):
        old_date = (date.today() - timedelta(days=30)).isoformat()
        history = {"researches": [{"date": old_date}]}
        assert _has_recent_research(history, 7) is False

    def test_empty(self):
        assert _has_recent_research({}, 7) is False


class TestHasExitAlert:
    def test_no_health_checks(self):
        assert _has_exit_alert({}) is False
        assert _has_exit_alert({"health_checks": []}) is False

    def test_health_check_with_recent_lesson(self):
        today = date.today().isoformat()
        history = {
            "health_checks": [{"date": today}],
            "notes": [{"type": "lesson", "date": today}],
        }
        assert _has_exit_alert(history) is True

    def test_health_check_without_lesson(self):
        today = date.today().isoformat()
        history = {
            "health_checks": [{"date": today}],
            "notes": [],
        }
        assert _has_exit_alert(history) is False


class TestThesisNeedsReview:
    def test_old_thesis(self):
        old_date = (date.today() - timedelta(days=100)).isoformat()
        history = {"notes": [{"type": "thesis", "date": old_date}]}
        assert _thesis_needs_review(history, 90) is True

    def test_recent_thesis(self):
        recent_date = (date.today() - timedelta(days=30)).isoformat()
        history = {"notes": [{"type": "thesis", "date": recent_date}]}
        assert _thesis_needs_review(history, 90) is False

    def test_no_thesis(self):
        history = {"notes": [{"type": "observation", "date": "2026-01-01"}]}
        assert _thesis_needs_review(history, 90) is False


class TestHasConcernNotes:
    def test_has_concern(self):
        history = {"notes": [{"type": "concern", "content": "PER 너무 낮음"}]}
        assert _has_concern_notes(history) is True

    def test_no_concern(self):
        history = {"notes": [{"type": "thesis"}]}
        assert _has_concern_notes(history) is False

    def test_empty(self):
        assert _has_concern_notes({}) is False


# ===================================================================
# Skill recommendation tests
# ===================================================================

class TestRecommendSkill:
    def test_holding_stock(self):
        """보유 종목 → health 추천"""
        history = {"trades": [{"type": "buy", "shares": 100}]}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "health"
        assert rel == "보유"

    def test_holding_with_old_thesis(self):
        """보유 + 테제 3개월 경과 → health + 리뷰 권고"""
        old_date = (date.today() - timedelta(days=100)).isoformat()
        history = {
            "trades": [{"type": "buy", "shares": 100}],
            "notes": [{"type": "thesis", "date": old_date}],
        }
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "health"
        assert "리뷰" in reason

    def test_exit_alert(self):
        """EXIT 판정 → screen_alternative"""
        today = date.today().isoformat()
        history = {
            "health_checks": [{"date": today}],
            "notes": [{"type": "lesson", "date": today}],
        }
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "screen_alternative"

    def test_bookmarked(self):
        """워치 중 → report"""
        history = {}
        skill, reason, rel = _recommend_skill(history, True)
        assert skill == "report"
        assert rel == "워치중"

    def test_frequent_screening(self):
        """3회 이상 스크리닝 → report + 주목"""
        history = {"screens": [
            {"date": "2026-01-01"},
            {"date": "2026-01-15"},
            {"date": "2026-02-01"},
        ]}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "report"
        assert rel == "주목"

    def test_recent_research(self):
        """최근 리서치 완료 → report_diff"""
        today = date.today().isoformat()
        history = {"researches": [{"date": today}]}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "report_diff"
        assert rel == "리서치완료"

    def test_concern_notes(self):
        """우려 메모 있음 → report"""
        history = {"notes": [{"type": "concern"}]}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "report"
        assert rel == "우려있음"

    def test_known_stock(self):
        """과거 데이터 있음 → report"""
        history = {"reports": [{"date": "2026-01-01"}]}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "report"
        assert rel == "기존"

    def test_unknown_stock(self):
        """미지의 종목 → report"""
        history = {}
        skill, reason, rel = _recommend_skill(history, False)
        assert skill == "report"
        assert rel == "미지"

    def test_is_held_parameter(self):
        """KIK-414: is_held=True → health (even with no trade history)"""
        history = {}
        skill, reason, rel = _recommend_skill(history, False, is_held=True)
        assert skill == "health"
        assert rel == "보유"

    def test_is_held_with_old_thesis(self):
        """KIK-414: is_held=True + old thesis → health + review"""
        from datetime import date, timedelta
        old_date = (date.today() - timedelta(days=100)).isoformat()
        history = {"notes": [{"type": "thesis", "date": old_date}]}
        skill, reason, rel = _recommend_skill(history, False, is_held=True)
        assert skill == "health"
        assert "리뷰" in reason


# ===================================================================
# KIK-427: Freshness detection tests
# ===================================================================

class TestFreshHours:
    def test_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _fresh_hours() == 24

    def test_custom_value(self):
        with patch.dict("os.environ", {"CONTEXT_FRESH_HOURS": "12"}):
            assert _fresh_hours() == 12

    def test_invalid_value(self):
        with patch.dict("os.environ", {"CONTEXT_FRESH_HOURS": "abc"}):
            assert _fresh_hours() == 24

    def test_empty_string(self):
        with patch.dict("os.environ", {"CONTEXT_FRESH_HOURS": ""}):
            assert _fresh_hours() == 24


class TestRecentHours:
    def test_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _recent_hours() == 168

    def test_custom_value(self):
        with patch.dict("os.environ", {"CONTEXT_RECENT_HOURS": "72"}):
            assert _recent_hours() == 72

    def test_invalid_value(self):
        with patch.dict("os.environ", {"CONTEXT_RECENT_HOURS": "xyz"}):
            assert _recent_hours() == 168


class TestHoursSince:
    def test_today(self):
        today = date.today().isoformat()
        h = _hours_since(today)
        assert 0 <= h < 25  # within today

    def test_yesterday(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        h = _hours_since(yesterday)
        assert 23 < h < 49

    def test_invalid_date(self):
        assert _hours_since("not-a-date") == 999999

    def test_none(self):
        assert _hours_since(None) == 999999

    def test_empty_string(self):
        assert _hours_since("") == 999999


class TestFreshnessLabel:
    def test_fresh(self):
        """오늘 데이터 → FRESH"""
        today = date.today().isoformat()
        assert freshness_label(today) == "FRESH"

    def test_recent(self):
        """3일 전 데이터 → RECENT"""
        three_days_ago = (date.today() - timedelta(days=3)).isoformat()
        assert freshness_label(three_days_ago) == "RECENT"

    def test_stale(self):
        """30일 전 데이터 → STALE"""
        old_date = (date.today() - timedelta(days=30)).isoformat()
        assert freshness_label(old_date) == "STALE"

    def test_none_date(self):
        """빈 문자열 → NONE"""
        assert freshness_label("") == "NONE"
        assert freshness_label(None) == "NONE"

    def test_custom_thresholds(self):
        """환경 변수로 임계값 커스터마이즈"""
        two_days_ago = (date.today() - timedelta(days=2)).isoformat()
        # Default: 24h fresh → 2 days ago is RECENT
        assert freshness_label(two_days_ago) == "RECENT"
        # Custom: 72h fresh → 2 days ago is FRESH
        with patch.dict("os.environ", {"CONTEXT_FRESH_HOURS": "72"}):
            assert freshness_label(two_days_ago) == "FRESH"

    def test_boundary_stale(self):
        """정확히 7일+1일 전 → STALE"""
        eight_days_ago = (date.today() - timedelta(days=8)).isoformat()
        assert freshness_label(eight_days_ago) == "STALE"


class TestFreshnessAction:
    def test_fresh(self):
        assert freshness_action("FRESH") == "컨텍스트 활용"

    def test_recent(self):
        assert freshness_action("RECENT") == "차분 모드 권장"

    def test_stale(self):
        assert freshness_action("STALE") == "전체 재조회 권장"

    def test_none(self):
        assert freshness_action("NONE") == "신규 조회"

    def test_unknown(self):
        assert freshness_action("UNKNOWN") == "신규 조회"


# ===================================================================
# KIK-428: Action directive tests
# ===================================================================

class TestActionDirective:
    def test_fresh(self):
        d = _action_directive("FRESH")
        assert "⛔" in d
        assert "스킬 실행 불필요" in d

    def test_recent(self):
        d = _action_directive("RECENT")
        assert "⚡" in d
        assert "차분 모드" in d

    def test_stale(self):
        d = _action_directive("STALE")
        assert "🔄" in d
        assert "전체 재조회" in d

    def test_none(self):
        d = _action_directive("NONE")
        assert "🆕" in d
        assert "스킬을 실행" in d

    def test_unknown_falls_back_to_none(self):
        d = _action_directive("UNKNOWN")
        assert "🆕" in d


class TestBestFreshness:
    def test_empty(self):
        assert _best_freshness([]) == "NONE"

    def test_single(self):
        assert _best_freshness(["STALE"]) == "STALE"

    def test_fresh_wins(self):
        assert _best_freshness(["STALE", "FRESH", "RECENT"]) == "FRESH"

    def test_recent_over_stale(self):
        assert _best_freshness(["STALE", "RECENT"]) == "RECENT"

    def test_all_none(self):
        assert _best_freshness(["NONE", "NONE"]) == "NONE"


# ===================================================================
# Context formatting tests
# ===================================================================

class TestFormatContext:
    def test_with_data(self):
        """이력 있음 → screens/reports/trades + 신선도 라벨 포함"""
        today = date.today().isoformat()
        history = {
            "screens": [{"date": today, "preset": "alpha", "region": "kr"}],
            "reports": [{"date": today, "score": 75, "verdict": "저평가"}],
            "trades": [{"date": today, "type": "buy", "shares": 100, "price": 2850}],
            "health_checks": [],
            "notes": [],
            "themes": ["EV", "자동차"],
            "researches": [],
        }
        md = _format_context("005930.KS", history, "health", "보유", "보유")
        assert "005930.KS" in md
        assert "alpha" in md
        assert "점수 75" in md
        assert "매수" in md
        assert "EV" in md
        # KIK-427: freshness labels
        assert "[FRESH]" in md
        assert "신선도 요약" in md
        assert "컨텍스트 활용" in md
        # KIK-428: action directive at the top
        assert md.startswith("⛔ FRESH")
        assert "스킬 실행 불필요" in md

    def test_empty_history(self):
        """빈 이력 → 과거 데이터 없음 + NONE directive"""
        history = {}
        md = _format_context("AAPL", history, "report", "미지", "미지")
        assert "AAPL" in md
        assert "과거 데이터 없음" in md
        # No freshness summary when no data
        assert "신선도 요약" not in md
        # KIK-428: NONE directive
        assert md.startswith("🆕 NONE")
        assert "스킬을 실행" in md

    def test_notes_truncated(self):
        """긴 메모 → 50자로 잘림"""
        history = {"notes": [{"type": "thesis", "content": "A" * 100}]}
        md = _format_context("005930.KS", history, "report", "기존", "기존")
        assert "A" * 50 in md
        assert "A" * 51 not in md

    def test_stale_data_shows_stale_label(self):
        """오래된 데이터 → [STALE] 라벨 + 전체 재조회 권장 + STALE directive"""
        old_date = (date.today() - timedelta(days=30)).isoformat()
        history = {
            "reports": [{"date": old_date, "score": 50, "verdict": "적정"}],
        }
        md = _format_context("005930.KS", history, "report", "기존", "기존")
        assert "[STALE]" in md
        assert "전체 재조회 권장" in md
        # KIK-428: STALE directive
        assert md.startswith("🔄 STALE")

    def test_recent_data_shows_recent_label(self):
        """3일 전 데이터 → [RECENT] 라벨 + 차분 모드 권장 + RECENT directive"""
        recent_date = (date.today() - timedelta(days=3)).isoformat()
        history = {
            "researches": [{"date": recent_date, "research_type": "stock",
                            "summary": "test"}],
        }
        md = _format_context("005930.KS", history, "report", "기존", "기존")
        assert "[RECENT]" in md
        assert "차분 모드 권장" in md
        # KIK-428: RECENT directive
        assert md.startswith("⚡ RECENT")


class TestFormatMarketContext:
    def test_basic(self):
        today = date.today().isoformat()
        mc = {
            "date": today,
            "indices": [
                {"name": "KOSPI", "price": 2650},
                {"name": "S&P 500", "price": 5200},
            ],
        }
        md = _format_market_context(mc)
        assert "시황 컨텍스트" in md
        assert "KOSPI" in md
        assert "2650" in md
        # KIK-427: freshness label
        assert "[FRESH]" in md
        assert "컨텍스트 활용" in md
        # KIK-428: action directive at the top
        assert md.startswith("⛔ FRESH")
        assert "스킬 실행 불필요" in md

    def test_empty_indices(self):
        mc = {"date": "2026-02-17", "indices": []}
        md = _format_market_context(mc)
        assert "2026-02-17" in md

    def test_stale_market_context(self):
        """오래된 시황 데이터 → [STALE] + STALE directive"""
        old_date = (date.today() - timedelta(days=30)).isoformat()
        mc = {"date": old_date, "indices": []}
        md = _format_market_context(mc)
        assert "[STALE]" in md
        assert "전체 재조회 권장" in md
        # KIK-428: STALE directive
        assert md.startswith("🔄 STALE")


# ===================================================================
# Resolve symbol (with Neo4j mock)
# ===================================================================

class TestResolveSymbol:
    def test_direct_ticker(self):
        """티커 패턴이 있으면 Neo4j 조회 불필요"""
        assert _resolve_symbol("005930.KS 어때?") == "005930.KS"

    @patch("src.data.context.auto_context.graph_store")
    def test_name_lookup_found(self, mock_gs):
        """회사명 → Neo4j 역조회로 찾음"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_record = {"symbol": "005930.KS"}
        mock_session.run.return_value.single.return_value = mock_record
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = _resolve_symbol("삼성전자 상황은?")
        assert result == "005930.KS"

    @patch("src.data.context.auto_context.graph_store")
    def test_name_lookup_not_found(self, mock_gs):
        """회사명 → Neo4j 에 없음 → None"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = None
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = _resolve_symbol("정체불명 회사 상황은?")
        assert result is None

    @patch("src.data.context.auto_context.graph_store")
    def test_neo4j_unavailable(self, mock_gs):
        """Neo4j 미접속 → None"""
        mock_gs._get_driver.return_value = None
        result = _resolve_symbol("삼성전자 상황은?")
        assert result is None


# ===================================================================
# Check bookmarked (with Neo4j mock)
# ===================================================================

class TestCheckBookmarked:
    @patch("src.data.context.auto_context.graph_store")
    def test_bookmarked(self, mock_gs):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = {"cnt": 1}
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        assert _check_bookmarked("005930.KS") is True

    @patch("src.data.context.auto_context.graph_store")
    def test_not_bookmarked(self, mock_gs):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = {"cnt": 0}
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        assert _check_bookmarked("005930.KS") is False

    @patch("src.data.context.auto_context.graph_store")
    def test_neo4j_unavailable(self, mock_gs):
        mock_gs._get_driver.return_value = None
        assert _check_bookmarked("005930.KS") is False


# ===================================================================
# get_context integration tests (all mocked)
# ===================================================================

class TestGetContext:
    @patch("src.data.context.auto_context.graph_query")
    def test_market_query(self, mock_gq):
        """시황 쿼리 → market-research 추천"""
        mock_gq.get_recent_market_context.return_value = {
            "date": "2026-02-17",
            "indices": [{"name": "KOSPI", "price": 2650}],
        }
        result = get_context("오늘 시황은?")
        assert result is not None
        assert result["recommended_skill"] == "market-research"
        assert result["relationship"] == "시황"
        assert "KOSPI" in result["context_markdown"]

    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context.graph_query")
    def test_market_query_no_data(self, mock_gq, mock_vs):
        """시황 쿼리 + 데이터 없음 → None"""
        mock_gq.get_recent_market_context.return_value = None
        result = get_context("시황 어때?")
        assert result is None

    @patch("src.data.context.auto_context.graph_query")
    def test_portfolio_query(self, mock_gq):
        """PF 쿼리 → health 추천"""
        mock_gq.get_recent_market_context.return_value = {
            "date": "2026-02-17",
        }
        result = get_context("PF 괜찮아?")
        assert result is not None
        assert result["recommended_skill"] == "health"
        assert result["relationship"] == "PF"

    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_symbol_query_holding(self, mock_gs, mock_bookmark):
        """보유 종목 쿼리 → health 추천"""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {
            "trades": [{"type": "buy", "shares": 100}],
        }
        mock_bookmark.return_value = False

        result = get_context("005930.KS 어때?")
        assert result is not None
        assert result["symbol"] == "005930.KS"
        assert result["recommended_skill"] == "health"
        assert result["relationship"] == "보유"

    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_symbol_query_unknown(self, mock_gs, mock_bookmark):
        """미지 종목 → report 추천"""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bookmark.return_value = False

        result = get_context("AAPL 조사해줘")
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["recommended_skill"] == "report"
        assert result["relationship"] == "미지"

    @patch("src.data.context.auto_context._vector_search", return_value=[])
    def test_no_symbol_detected(self, mock_vs):
        """심볼 미검출 → None (Neo4j 조회도 스킵)"""
        # _lookup_symbol_by_name will try Neo4j but it's not available
        with patch("src.data.context.auto_context.graph_store") as mock_gs:
            mock_gs._get_driver.return_value = None
            result = get_context("오늘은 날씨가 좋다")
        assert result is None

    @patch("src.data.context.auto_context.build_symbol_context_local",
           return_value=None)
    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_neo4j_unavailable(self, mock_gs, mock_bookmark, mock_vs,
                                mock_local):
        """Neo4j 미접속 시 로컬 data/ 로 폴백 (KIK-719).
        여기서는 로컬에도 정보가 없는 경우 None 을 반환하는지 확인."""
        mock_gs._get_driver.return_value = None  # for _resolve_symbol
        mock_gs.is_available.return_value = False

        result = get_context("005930.KS 어때?")
        # 로컬 폴백도 비어 있음 → None
        assert result is None
        # 폴백 함수가 호출되었는지 확인
        mock_local.assert_called_once_with("005930.KS")

    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_bookmarked_stock(self, mock_gs, mock_bookmark):
        """워치 중 → report + 워치중"""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bookmark.return_value = True

        result = get_context("005930.KS 어때?")
        assert result is not None
        assert result["recommended_skill"] == "report"
        assert result["relationship"] == "워치중"

    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_context_includes_all_fields(self, mock_gs, mock_bookmark):
        """반환값에 필요한 모든 필드가 포함된다"""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bookmark.return_value = False

        result = get_context("AAPL 상황")
        assert result is not None
        assert "symbol" in result
        assert "context_markdown" in result
        assert "recommended_skill" in result
        assert "recommendation_reason" in result
        assert "relationship" in result


# ===================================================================
# KIK-420: Vector search helper tests
# ===================================================================


class TestVectorSearch:
    """Tests for _vector_search() function."""

    def test_tei_unavailable_returns_empty(self):
        """TEI 미기동 → 빈 리스트"""
        with patch("src.data.embedding_client.is_available", return_value=False):
            result = _vector_search("test query")
        assert result == []

    @patch("src.data.context.auto_context.graph_query")
    def test_tei_available_returns_results(self, mock_gq):
        """TEI + Neo4j 정상 → 벡터 검색 결과"""
        mock_gq.vector_search.return_value = [
            {"label": "Report", "summary": "005930.KS 삼성전자", "score": 0.92,
             "date": "2026-02-18", "id": "r1", "symbol": "005930.KS"},
        ]
        with patch("src.data.embedding_client.is_available", return_value=True), \
             patch("src.data.embedding_client.get_embedding",
                   return_value=[0.1] * 384):
            result = _vector_search("삼성전자 리포트")
        assert len(result) == 1
        assert result[0]["label"] == "Report"

    @patch("src.data.context.auto_context.graph_query")
    def test_embedding_failure_returns_empty(self, mock_gq):
        """TEI is available but embedding fails → 빈 리스트"""
        with patch("src.data.embedding_client.is_available", return_value=True), \
             patch("src.data.embedding_client.get_embedding", return_value=None):
            result = _vector_search("test")
        assert result == []


class TestFormatVectorResults:
    """Tests for _format_vector_results()."""

    def test_formats_results(self):
        today = date.today().isoformat()
        results = [
            {"label": "Screen", "summary": "kr alpha",
             "score": 0.95, "date": today, "id": "s1"},
            {"label": "Report", "summary": "005930.KS 삼성전자 / 저평가(72.5)",
             "score": 0.88, "date": today, "id": "r1"},
        ]
        md = _format_vector_results(results)
        assert "관련 과거 기록" in md
        assert "[Screen]" in md
        assert "[Report]" in md
        assert "95%" in md
        assert "88%" in md
        # KIK-427: freshness labels
        assert "[FRESH]" in md

    def test_empty_results(self):
        md = _format_vector_results([])
        assert "관련 과거 기록" in md

    def test_none_summary_handled(self):
        results = [{"label": "Note", "summary": None, "score": 0.5,
                     "date": "2026-01-01", "id": "n1"}]
        md = _format_vector_results(results)
        assert "(요약 없음)" in md

    def test_stale_vector_result(self):
        """오래된 벡터 결과 → [STALE] 라벨"""
        old_date = (date.today() - timedelta(days=30)).isoformat()
        results = [{"label": "Report", "summary": "old report",
                     "score": 0.75, "date": old_date, "id": "r1"}]
        md = _format_vector_results(results)
        assert "[STALE]" in md

    def test_no_date_shows_none(self):
        """날짜 없는 벡터 결과 → [NONE] 라벨"""
        results = [{"label": "Note", "summary": "note", "score": 0.6,
                     "date": "", "id": "n1"}]
        md = _format_vector_results(results)
        assert "[NONE]" in md


class TestInferSkillFromVectors:
    """Tests for _infer_skill_from_vectors()."""

    def test_report_majority(self):
        results = [
            {"label": "Report"}, {"label": "Report"}, {"label": "Screen"},
        ]
        assert _infer_skill_from_vectors(results) == "report"

    def test_screen_majority(self):
        results = [
            {"label": "Screen"}, {"label": "Screen"}, {"label": "Report"},
        ]
        assert _infer_skill_from_vectors(results) == "screen-stocks"

    def test_trade_majority(self):
        results = [{"label": "Trade"}, {"label": "Trade"}]
        assert _infer_skill_from_vectors(results) == "health"

    def test_research_majority(self):
        results = [{"label": "Research"}, {"label": "MarketContext"}]
        assert _infer_skill_from_vectors(results) == "market-research"

    def test_empty_returns_report(self):
        assert _infer_skill_from_vectors([]) == "report"


class TestMergeContext:
    """Tests for _merge_context()."""

    def test_both_none(self):
        assert _merge_context(None, []) is None

    def test_symbol_only(self):
        ctx = {"symbol": "005930.KS", "context_markdown": "## Report"}
        result = _merge_context(ctx, [])
        assert result == ctx

    def test_vector_only(self):
        vectors = [
            {"label": "Screen", "summary": "kr alpha",
             "score": 0.9, "date": "2026-02-18", "id": "s1"},
        ]
        result = _merge_context(None, vectors)
        assert result is not None
        assert result["symbol"] == ""
        assert "관련 과거 기록" in result["context_markdown"]
        assert result["recommendation_reason"] == "벡터 유사도 검색"
        # KIK-428: action directive present
        assert "FRESH" in result["context_markdown"] or \
               "RECENT" in result["context_markdown"] or \
               "STALE" in result["context_markdown"]

    def test_both_merged(self):
        ctx = {
            "symbol": "005930.KS",
            "context_markdown": "## 005930.KS Context",
            "recommended_skill": "health",
            "recommendation_reason": "보유",
            "relationship": "보유",
        }
        vectors = [
            {"label": "Report", "summary": "prev report",
             "score": 0.85, "date": "2026-02-10", "id": "r1"},
        ]
        result = _merge_context(ctx, vectors)
        assert result is not None
        assert result["symbol"] == "005930.KS"
        assert "## 005930.KS Context" in result["context_markdown"]
        assert "관련 과거 기록" in result["context_markdown"]
        assert result["recommended_skill"] == "health"  # symbol context takes priority


class TestGetContextWithVectors:
    """Integration tests for get_context() with vector search (KIK-420)."""

    @patch("src.data.context.auto_context._vector_search")
    @patch("src.data.context.auto_context.graph_store")
    def test_no_symbol_with_vectors(self, mock_gs, mock_vs):
        """심볼 없음 + 벡터 결과 있음 → 벡터만 반환"""
        mock_gs._get_driver.return_value = None  # no Neo4j for name lookup
        mock_vs.return_value = [
            {"label": "Screen", "summary": "kr alpha 반도체",
             "score": 0.88, "date": "2026-02-18", "id": "s1",
             "symbol": None},
        ]
        result = get_context("전에 조사했던 반도체 관련 종목")
        assert result is not None
        assert result["symbol"] == ""
        assert "관련 과거 기록" in result["context_markdown"]

    @patch("src.data.context.auto_context._vector_search")
    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_symbol_with_vectors(self, mock_gs, mock_bm, mock_vs):
        """심볼 있음 + 벡터 결과 있음 → 통합"""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bm.return_value = False
        mock_vs.return_value = [
            {"label": "Report", "summary": "prev AAPL report",
             "score": 0.91, "date": "2026-01-15", "id": "r1",
             "symbol": "AAPL"},
        ]
        result = get_context("AAPL 조사해줘")
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert "관련 과거 기록" in result["context_markdown"]

    @patch("src.data.context.auto_context._vector_search")
    @patch("src.data.context.auto_context.graph_query")
    def test_market_query_with_vectors(self, mock_gq, mock_vs):
        """시황 쿼리 + 벡터 결과 → 통합"""
        mock_gq.get_recent_market_context.return_value = {
            "date": "2026-02-17",
            "indices": [{"name": "KOSPI", "price": 2650}],
        }
        mock_vs.return_value = [
            {"label": "MarketContext", "summary": "prev context",
             "score": 0.87, "date": "2026-02-10", "id": "mc1",
             "symbol": None},
        ]
        result = get_context("오늘 시황은?")
        assert result is not None
        assert "KOSPI" in result["context_markdown"]
        assert "관련 과거 기록" in result["context_markdown"]

    @patch("src.data.context.auto_context._vector_search")
    @patch("src.data.context.auto_context.graph_store")
    def test_no_symbol_no_vectors(self, mock_gs, mock_vs):
        """심볼 없음 + 벡터 없음 → None"""
        mock_gs._get_driver.return_value = None
        mock_vs.return_value = []
        result = get_context("오늘은 날씨가 좋다")
        assert result is None


# ===================================================================
# KIK-534: Investment lesson context tests
# ===================================================================

class TestFormatLessonSection:
    """Tests for _format_lesson_section()."""

    def test_empty_lessons(self):
        """lesson 이 비어 있음 → 빈 문자열."""
        assert _format_lesson_section([]) == ""

    def test_lesson_with_trigger_and_expected_action(self):
        """trigger + expected_action → 화살표로 표시."""
        lessons = [{
            "symbol": "005930.KS",
            "trigger": "RSI70 초과에서 매수",
            "expected_action": "RSI70 초과에서는 매수 안 함",
            "content": "고점 매수했다",
            "date": "2026-02-15",
        }]
        md = _format_lesson_section(lessons)
        assert "## 투자 lesson" in md
        assert "[005930.KS]" in md
        assert "RSI70 초과에서 매수" in md
        assert "→" in md
        assert "RSI70 초과에서는 매수 안 함" in md
        assert "2026-02-15" in md

    def test_lesson_with_trigger_only(self):
        """trigger 만."""
        lessons = [{
            "trigger": "모멘텀에 추격 매수했다",
            "content": "손절",
            "date": "2026-02-10",
        }]
        md = _format_lesson_section(lessons)
        assert "트리거: 모멘텀에 추격 매수했다" in md
        assert "손절" in md

    def test_lesson_with_expected_action_only(self):
        """expected_action 만."""
        lessons = [{
            "expected_action": "거래량 확인 후 진입",
            "content": "반성",
            "date": "2026-02-10",
        }]
        md = _format_lesson_section(lessons)
        assert "다음: 거래량 확인 후 진입" in md

    def test_lesson_without_extra_fields(self):
        """trigger/expected_action 없음 → content 만."""
        lessons = [{
            "symbol": "AAPL",
            "content": "Don't chase momentum",
            "date": "2026-01-01",
        }]
        md = _format_lesson_section(lessons)
        assert "## 투자 lesson" in md
        assert "[AAPL]" in md
        assert "Don't chase momentum" in md

    def test_max_5_lessons(self):
        """최대 5건으로 제한."""
        lessons = [
            {"content": f"lesson {i}", "date": f"2026-02-{i:02d}"}
            for i in range(1, 8)
        ]
        md = _format_lesson_section(lessons)
        assert "lesson 5" in md
        assert "lesson 6" not in md

    def test_no_symbol_no_bracket(self):
        """symbol 없음 → 대괄호 없음."""
        lessons = [{"content": "General lesson", "date": "2026-01-01"}]
        md = _format_lesson_section(lessons)
        assert "[]" not in md
        assert "General lesson" in md


class TestLoadLessons:
    """Tests for _load_lessons()."""

    @patch("src.data.context.auto_context.note_manager")
    def test_load_lessons_returns_list(self, mock_nm):
        """lesson 을 로드해 리스트를 반환."""
        mock_nm.load_notes.return_value = [{
            "symbol": "005930.KS", "type": "lesson",
            "content": "test lesson",
            "trigger": "bought high",
            "expected_action": "wait for dip",
            "date": "2026-02-28",
        }]
        result = _load_lessons("005930.KS")
        assert len(result) == 1
        assert result[0]["trigger"] == "bought high"
        mock_nm.load_notes.assert_called_once_with(note_type="lesson", symbol="005930.KS")

    @patch("src.data.context.auto_context.note_manager")
    def test_load_lessons_graceful_degradation(self, mock_nm):
        """load_notes 오류 → 빈 리스트."""
        mock_nm.load_notes.side_effect = Exception("fail")
        result = _load_lessons()
        assert result == []


class TestGetContextWithLessons:
    """Integration test: get_context appends lesson section."""

    @patch("src.data.context.auto_context._load_lessons")
    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_lesson_appended_to_context(self, mock_gs, mock_bm, mock_lessons):
        """lesson 섹션이 컨텍스트에 추가되어야 한다."""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bm.return_value = False
        mock_lessons.return_value = [{
            "symbol": "005930.KS",
            "trigger": "고점매수",
            "expected_action": "RSI 확인",
            "content": "반성",
            "date": "2026-02-15",
        }]
        result = get_context("005930.KS 어때?")
        assert result is not None
        assert "## 투자 lesson" in result["context_markdown"]
        assert "고점매수" in result["context_markdown"]
        assert "RSI 확인" in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons")
    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_no_lessons_no_section(self, mock_gs, mock_bm, mock_lessons):
        """lesson 없음 → 섹션 비표시."""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bm.return_value = False
        mock_lessons.return_value = []
        result = get_context("AAPL 조사해줘")
        assert result is not None
        assert "## 투자 lesson" not in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons", side_effect=Exception("fail"))
    @patch("src.data.context.auto_context._check_bookmarked")
    @patch("src.data.context.auto_context.graph_store")
    def test_lesson_error_graceful_degradation(self, mock_gs, mock_bm, mock_les):
        """lesson 로드 오류 → graceful degradation (섹션 없음)."""
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = {}
        mock_gs.is_held.return_value = False
        mock_bm.return_value = False
        result = get_context("005930.KS 어때?")
        assert result is not None
        assert "## 투자 lesson" not in result["context_markdown"]

    # --- KIK-554: PF/시황 쿼리에서도 lesson 표시 ---

    @patch("src.data.context.auto_context._load_lessons")
    @patch("src.data.context.auto_context.graph_query")
    def test_lesson_appended_to_portfolio_query(self, mock_gq, mock_lessons):
        """PF 쿼리에서도 lesson 이 부여되어야 한다 (KIK-554)."""
        mock_gq.get_recent_market_context.return_value = {"date": "2026-03-19"}
        mock_lessons.return_value = [{
            "symbol": "",
            "trigger": "매수 직후 경고를 맹신하지 않기",
            "expected_action": "테제 지표 확인 후 판단",
            "content": "lesson",
            "date": "2026-03-15",
        }]
        result = get_context("포트폴리오 헬스체크")
        assert result is not None
        assert "## 투자 lesson" in result["context_markdown"]
        assert "매수 직후 경고를 맹신하지 않기" in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons")
    @patch("src.data.context.auto_context.graph_query")
    def test_lesson_appended_to_market_query(self, mock_gq, mock_lessons):
        """시황 쿼리에서도 lesson 이 부여되어야 한다 (KIK-554)."""
        mock_gq.get_recent_market_context.return_value = {"date": "2026-03-19"}
        mock_lessons.return_value = [{
            "symbol": "",
            "trigger": "급락 시 패닉 매도했다",
            "expected_action": "침착하게 기다린다",
            "content": "lesson",
            "date": "2026-03-10",
        }]
        result = get_context("시황 확인")
        assert result is not None
        assert "## 투자 lesson" in result["context_markdown"]
        assert "급락 시 패닉 매도했다" in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons")
    @patch("src.data.context.auto_context.graph_query")
    def test_pf_query_no_lessons_no_section(self, mock_gq, mock_lessons):
        """PF 쿼리에서 lesson 비어 있음 → 섹션 비표시."""
        mock_gq.get_recent_market_context.return_value = None
        mock_lessons.return_value = []
        result = get_context("PF 체크")
        assert result is not None
        assert "## 투자 lesson" not in result["context_markdown"]

    # --- KIK-563: PF 쿼리에서 보유 종목 주요 메모 표시 ---

    @patch("src.data.context.auto_context._load_lessons", return_value=[])
    @patch("src.data.graph_query.portfolio.get_holdings_notes")
    @patch("src.data.context.auto_context.graph_store")
    @patch("src.data.context.auto_context.graph_query")
    def test_pf_query_shows_holdings_notes(self, mock_gq, mock_gs, mock_notes,
                                            mock_les):
        """PF 쿼리에서 보유 종목의 Note(observation/concern/target)가 표시된다 (KIK-563).

        Neo4j 접속 중인 경로를 테스트 (KIK-719)."""
        mock_gs.is_available.return_value = True
        mock_gq.get_recent_market_context.return_value = {"date": "2026-03-20"}
        mock_notes.return_value = [
            {"symbol": "NFLX", "type": "observation",
             "content": "추가 매수 계획 중단 — 30주에서 멈춤", "date": "2026-03-19"},
            {"symbol": "NVDA", "type": "thesis",
             "content": "AI 반도체 지배적 포지션, PEG<1", "date": "2026-03-19"},
        ]
        result = get_context("포트폴리오 평가")
        assert result is not None
        md = result["context_markdown"]
        assert "## 보유 종목 주요 메모" in md
        assert "[NFLX] observation" in md
        assert "추가 매수 계획 중단" in md
        assert "[NVDA] thesis" in md

    @patch("src.data.context.auto_context._load_lessons", return_value=[])
    @patch("src.data.graph_query.portfolio.get_holdings_notes")
    @patch("src.data.context.auto_context.graph_store")
    @patch("src.data.context.auto_context.graph_query")
    def test_pf_query_no_notes_no_section(self, mock_gq, mock_gs, mock_notes,
                                           mock_les):
        """보유 종목에 메모 없음 → 섹션 비표시 (Neo4j 접속 중)."""
        mock_gs.is_available.return_value = True
        mock_gq.get_recent_market_context.return_value = None
        mock_notes.return_value = []
        result = get_context("PF 체크")
        assert result is not None
        assert "## 보유 종목 주요 메모" not in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons", return_value=[])
    @patch("src.data.graph_query.portfolio.get_holdings_notes",
           side_effect=Exception("fail"))
    @patch("src.data.context.auto_context.graph_store")
    @patch("src.data.context.auto_context.graph_query")
    def test_pf_query_notes_error_graceful(self, mock_gq, mock_gs, mock_notes,
                                            mock_les):
        """Neo4j 접속 중이지만 get_holdings_notes 실패 → graceful degradation."""
        mock_gs.is_available.return_value = True
        mock_gq.get_recent_market_context.return_value = None
        result = get_context("PF 헬스체크")
        assert result is not None
        assert "## 보유 종목 주요 메모" not in result["context_markdown"]
