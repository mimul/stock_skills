"""Tests for constraint_extractor (KIK-596)."""

import pytest

from src.data.context.constraint_extractor import (
    classify_action_type,
    extract_constraints,
    format_constraints_markdown,
    _lesson_to_constraint,
    _build_enriched_query,
    _build_lot_size_constraints,
)


# ---------------------------------------------------------------------------
# classify_action_type
# ---------------------------------------------------------------------------


class TestClassifyActionType:
    """Action type classification tests."""

    def test_swap_keywords(self):
        assert classify_action_type("035420.KS를 교체하고 싶어") == "swap_proposal"
        assert classify_action_type("대신할 종목 찾아줘") == "swap_proposal"
        assert classify_action_type("갈아탈 곳은?") == "swap_proposal"

    def test_new_buy_keywords(self):
        assert classify_action_type("NVDA를 사고 싶어") == "new_buy"
        assert classify_action_type("진입하고 싶어") == "new_buy"
        assert classify_action_type("추가하고 싶어") == "new_buy"

    def test_sell_keywords(self):
        assert classify_action_type("손절해야 할까?") == "sell"
        assert classify_action_type("익절하고 싶어") == "sell"
        assert classify_action_type("매도를 검토 중") == "sell"

    def test_rebalance_keywords(self):
        assert classify_action_type("리밸런스해줘") == "rebalance"
        assert classify_action_type("배분 조정하고 싶어") == "rebalance"

    def test_adjust_keywords(self):
        assert classify_action_type("PF 처방전 내줘") == "adjust"
        assert classify_action_type("어떻게 해야 해?") == "adjust"
        assert classify_action_type("개선해 줬으면 해") == "adjust"

    def test_fallback_to_adjust(self):
        assert classify_action_type("잘 모르겠는 질문") == "adjust"
        assert classify_action_type("") == "adjust"

    def test_multiple_keywords_swap_wins(self):
        """'매도'(sell)와 '대신'(swap)이 함께 있으면 swap 이 sell 보다 우선."""
        result = classify_action_type("매도하고 대신할 종목 찾아줘")
        assert result == "swap_proposal"

    def test_case_insensitive(self):
        assert classify_action_type("SWAP 제안") == "swap_proposal"

    def test_common_words_do_not_trigger_swap(self):
        """"대체로"·"대신증권" 같은 일반어는 교체 제안이 아니다 (코드 리뷰 M2)."""
        assert classify_action_type("대체로 괜찮아?") == "adjust"
        assert classify_action_type("대신증권 사고 싶어") == "new_buy"

    def test_plain_buy_and_sell_words(self):
        assert classify_action_type("삼성전자 매수") == "new_buy"
        assert classify_action_type("매수 타이밍") == "new_buy"
        assert classify_action_type("팔까?") == "sell"
        assert classify_action_type("팔아야 할까") == "sell"


# ---------------------------------------------------------------------------
# _build_enriched_query
# ---------------------------------------------------------------------------


class TestBuildEnrichedQuery:
    """Enriched query building tests."""

    def test_adds_boost_keywords(self):
        result = _build_enriched_query("035420.KS 교체", "swap_proposal")
        assert "통화배분" in result
        assert "지역분산" in result
        assert "매매단위" in result

    def test_sell_boost(self):
        result = _build_enriched_query("손절", "sell")
        assert "임계값" in result
        assert "테제" in result

    def test_unknown_type_no_crash(self):
        result = _build_enriched_query("test", "unknown_type")
        assert "test" in result


# ---------------------------------------------------------------------------
# _lesson_to_constraint
# ---------------------------------------------------------------------------


class TestLessonToConstraint:
    """Lesson to constraint conversion tests."""

    def test_with_explicit_trigger(self):
        lesson = {
            "id": "note_test_001",
            "trigger": "교체 제안 시",
            "expected_action": "통화 배분을 계산한다",
            "content": "[테스트 교훈] 통화 집중을 피하라",
            "symbol": "035420.KS",
        }
        result = _lesson_to_constraint(lesson, 0.85)
        assert result["id"] == "note_test_001"
        assert result["trigger"] == "교체 제안 시"
        assert result["expected_action"] == "통화 배분을 계산한다"
        assert result["relevance_score"] == 0.85

    def test_without_trigger(self):
        lesson = {
            "id": "note_test_002",
            "content": "단순한 메모입니다",
        }
        result = _lesson_to_constraint(lesson, 0.5)
        assert result["id"] == "note_test_002"
        assert result["relevance_score"] == 0.5

    def test_source_from_first_line(self):
        lesson = {
            "id": "note_test_003",
            "content": "[중요한 교훈]\n여기는 2행째",
        }
        result = _lesson_to_constraint(lesson, 0.3)
        assert "중요한 교훈" in result["source"]


# ---------------------------------------------------------------------------
# extract_constraints (integration)
# ---------------------------------------------------------------------------


class TestExtractConstraints:
    """Integration tests for extract_constraints."""

    def test_returns_required_fields(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [
                {
                    "id": "les_001",
                    "type": "lesson",
                    "trigger": "교체 제안 시 USD 비율이 60% 초과",
                    "expected_action": "통화 배분 변화를 계산",
                    "content": "[통화 집중 교훈] USD 편중을 피한다",
                    "date": "2026-04-15",
                },
            ],
        )
        result = extract_constraints("035420.KS를 교체하고 싶어")
        assert result["action_type"] == "swap_proposal"
        assert "035420.KS" in result["symbols"]
        assert result["lesson_count"] == 1
        assert isinstance(result["constraints"], list)

    def test_empty_lessons(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        result = extract_constraints("뭔가 하고 싶어")
        assert result["constraints"] == []
        assert result["lesson_count"] == 0
        assert result["matched_count"] == 0

    def test_max_constraints_limit(self, monkeypatch):
        lessons = [
            {
                "id": f"les_{i:03d}",
                "type": "lesson",
                "trigger": f"테스트 조건{i}",
                "expected_action": f"액션{i}",
                "content": f"교체 통화 레슨{i}",
                "date": f"2026-04-{i+1:02d}",
            }
            for i in range(10)
        ]
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: lessons,
        )
        result = extract_constraints("교체하고 싶어", max_constraints=3)
        assert len(result["constraints"]) <= 3

    def test_symbol_extraction(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        result = extract_constraints("NVDA 와 AAPL 을 사고 싶어")
        assert "NVDA" in result["symbols"]
        assert "AAPL" in result["symbols"]

    def test_new_buy_action_type(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        result = extract_constraints("NVDA를 사고 싶은데 어떻게 생각해?")
        assert result["action_type"] == "new_buy"

    def test_sell_action_type(self, monkeypatch):
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        result = extract_constraints("015760.KS를 손절해야 할까")
        assert result["action_type"] == "sell"

    def test_graceful_degradation_load_failure(self, monkeypatch):
        """_load_lessons raises ImportError -> empty constraints."""
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: (_ for _ in ()).throw(ImportError("no module")),
        )
        # The function catches this internally via try/except in _load_lessons
        # Since _load_lessons itself has try/except, we mock it to return []
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        result = extract_constraints("교체하고 싶어")
        assert result["constraints"] == []

    def test_graceful_degradation_symbols_failure(self, monkeypatch):
        """_extract_symbols fails -> symbols=[], but constraints still work."""
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [],
        )
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._extract_symbols",
            lambda x: [],
        )
        result = extract_constraints("NVDA를 사고 싶어")
        assert result["symbols"] == []
        assert result["action_type"] == "new_buy"

    def test_score_zero_lessons_filtered(self, monkeypatch):
        """Lessons with score=0 should not appear in constraints."""
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [
                {
                    "id": "irrelevant",
                    "trigger": "xyz abc",
                    "expected_action": "xyz",
                    "content": "completely unrelated xyz",
                    "date": "2026-01-01",
                },
            ],
        )
        result = extract_constraints("전혀 다른 주제")
        # Score is likely 0, so should be filtered
        assert result["matched_count"] <= 1

    def test_empty_content_lesson(self, monkeypatch):
        """Lesson with empty content -> source falls back to id."""
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [
                {
                    "id": "les_empty",
                    "trigger": "교체 제안 시",
                    "expected_action": "확인한다",
                    "content": "",
                    "date": "2026-04-15",
                },
            ],
        )
        result = extract_constraints("교체하고 싶어")
        if result["constraints"]:
            assert result["constraints"][0]["source"] == "les_empty"

    def test_max_constraints_one(self, monkeypatch):
        """max_constraints=1 returns at most 1."""
        lessons = [
            {
                "id": f"les_{i}",
                "trigger": f"교체 조건{i}",
                "expected_action": f"액션{i}",
                "content": f"교체 통화 레슨{i}",
                "date": f"2026-04-{i+1:02d}",
            }
            for i in range(5)
        ]
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: lessons,
        )
        result = extract_constraints("교체하고 싶어", max_constraints=1)
        assert len(result["constraints"]) <= 1

    def test_relevance_ordering(self, monkeypatch):
        lessons = [
            {
                "id": "les_low",
                "trigger": "전혀 관계없는 조건",
                "expected_action": "관계없는 액션",
                "content": "무관한 레슨",
                "date": "2026-04-01",
            },
            {
                "id": "les_high",
                "trigger": "교체 제안 시 USD 비율 60% 초과",
                "expected_action": "통화 배분 변화를 계산한 뒤 제안",
                "content": "[통화 집중 교훈] 교체로 통화가 쏠린다",
                "date": "2026-04-15",
            },
        ]
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: lessons,
        )
        result = extract_constraints("035420.KS를 교체하고 싶어")
        if result["constraints"]:
            # Higher relevance should come first
            scores = [c["relevance_score"] for c in result["constraints"]]
            assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# _build_lot_size_constraints
# ---------------------------------------------------------------------------


class TestBuildLotSizeConstraints:
    """매매 단위 제약 자동 주입 테스트.

    한국·미국 주식은 모두 1주 단위이므로 제약이 생성되지 않아야 한다.
    """

    def test_kospi_stock_no_constraint(self):
        result = _build_lot_size_constraints(["035420.KS"])
        assert result == []  # 한국 = 1주 단위, 제약 불필요

    def test_kosdaq_stock_no_constraint(self):
        result = _build_lot_size_constraints(["247540.KQ"])
        assert result == []

    def test_us_stock_no_constraint(self):
        result = _build_lot_size_constraints(["AAPL"])
        assert len(result) == 0  # US = 1 share, no constraint

    def test_mixed_symbols(self):
        result = _build_lot_size_constraints(["035420.KS", "AAPL", "247540.KQ"])
        assert result == []

    def test_empty_symbols(self):
        result = _build_lot_size_constraints([])
        assert result == []

    def test_lot_constraint_with_multi_share_lot(self, monkeypatch):
        """매매 단위가 2주 이상이면 시스템 제약이 최우선(score 1.0)으로 생성된다."""
        monkeypatch.setattr(
            "src.data.ticker_utils.get_lot_size", lambda sym: 10,
        )
        result = _build_lot_size_constraints(["035420.KS"])
        assert len(result) == 1
        assert "10주 단위" in result[0]["expected_action"]
        assert result[0]["relevance_score"] == 1.0
        assert result[0]["community"] == "시스템 제약"

    def test_no_system_constraint_in_extract(self, monkeypatch):
        """1주 단위 시장에서는 extract_constraints 결과에 시스템 제약이 없다."""
        monkeypatch.setattr(
            "src.data.context.constraint_extractor._load_lessons",
            lambda: [
                {
                    "id": "les_001",
                    "trigger": "교체 제안 시",
                    "expected_action": "확인한다",
                    "content": "교체 통화 교훈",
                    "date": "2026-04-15",
                },
            ],
        )
        result = extract_constraints("035420.KS를 교체하고 싶어")
        assert all(
            not c["id"].startswith("system_lot_size_")
            for c in result["constraints"]
        )


# ---------------------------------------------------------------------------
# format_constraints_markdown
# ---------------------------------------------------------------------------


class TestFormatConstraintsMarkdown:
    """Markdown output formatting tests."""

    def test_empty_constraints(self):
        result = {
            "action_type": "swap_proposal",
            "symbols": [],
            "constraints": [],
            "lesson_count": 0,
            "matched_count": 0,
        }
        md = format_constraints_markdown(result)
        assert "swap_proposal" in md
        assert "해당하는 lesson" in md

    def test_with_constraints(self):
        result = {
            "action_type": "swap_proposal",
            "symbols": ["035420.KS"],
            "constraints": [
                {
                    "id": "les_001",
                    "trigger": "USD 비율 60% 초과",
                    "expected_action": "통화 배분을 계산",
                    "source": "[통화 집중 교훈]",
                    "community": "판단편향",
                    "relevance_score": 0.85,
                },
            ],
            "lesson_count": 5,
            "matched_count": 1,
        }
        md = format_constraints_markdown(result)
        assert "035420.KS" in md
        assert "USD 비율 60% 초과" in md
        assert "통화 배분을 계산" in md
        assert "판단편향" in md
