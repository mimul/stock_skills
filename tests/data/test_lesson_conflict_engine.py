"""Tests for unified lesson conflict engine (KIK-570)."""

import pytest


class TestTokenize:
    def test_english(self):
        from src.data.lesson_conflict import tokenize
        assert tokenize("hello world") == ["hello", "world"]

    def test_korean(self):
        from src.data.lesson_conflict import tokenize
        tokens = tokenize("고점매수RSI확인")
        assert "고점매수" in tokens
        assert "rsi" in tokens
        assert "확인" in tokens

    def test_korean_bigram(self):
        """조사가 붙은 어절도 바이그램으로 분해되어 부분 일치가 가능하다."""
        from src.data.lesson_conflict import tokenize
        tokens = tokenize("손절하는 기준")
        assert "손절하는" in tokens
        assert "손절" in tokens
        assert "기준" in tokens

    def test_mixed(self):
        from src.data.lesson_conflict import tokenize
        tokens = tokenize("VIX상승 → 관망")
        assert "vix" in tokens
        assert "상승" in tokens
        assert "관망" in tokens

    def test_empty(self):
        from src.data.lesson_conflict import tokenize
        assert tokenize("") == []


class TestKeywordSimilarityHangul:
    def test_korean_identical(self):
        from src.data.lesson_conflict import keyword_similarity
        assert keyword_similarity("고점매수", "고점매수") == pytest.approx(1.0)

    def test_korean_partial(self):
        from src.data.lesson_conflict import keyword_similarity
        sim = keyword_similarity("고점매수 RSI 높음", "고점매수 RSI 확인")
        assert sim > 0.3  # 공유: 고점매수, RSI

    def test_korean_disjoint(self):
        from src.data.lesson_conflict import keyword_similarity
        sim = keyword_similarity("금리상승", "반도체수요")
        assert sim == 0.0

    def test_old_split_would_fail(self):
        """단순 .split() 이라면 조사가 붙은 어절은 0.0 이 된다."""
        from src.data.lesson_conflict import keyword_similarity
        # 바이그램 분해가 없으면 "고점매수" 와 "고점매수RSI" 는 서로 다른 단일 토큰
        sim = keyword_similarity("고점매수", "고점매수RSI")
        assert sim > 0  # 한글 토크나이저가 중복을 찾아야 한다


class TestExtractTriggerAction:
    def test_structured_fields(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {"trigger": "VIX 상승", "expected_action": "관망"}
        assert extract_trigger(les) == "VIX 상승"
        assert extract_action(les) == "관망"

    def test_content_fallback(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {
            "content": "■trigger: 고점매수\n■expected_action: RSI 확인 후 매수",
            "trigger": "",
            "expected_action": "",
        }
        assert extract_trigger(les) == "고점매수"
        assert extract_action(les) == "RSI 확인 후 매수"

    def test_content_with_korean_labels(self):
        from src.data.lesson_conflict import extract_trigger, extract_action
        les = {
            "content": "트리거: 패닉 매도\n다음 액션: 침착하게 기다린다",
            "trigger": "",
            "expected_action": "",
        }
        assert extract_trigger(les) == "패닉 매도"
        assert extract_action(les) == "침착하게 기다린다"

    def test_no_trigger(self):
        from src.data.lesson_conflict import extract_trigger
        les = {"content": "일반적인 배움"}
        assert extract_trigger(les) == ""


class TestFindConflicts:
    def test_contradicting_action(self):
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "고점매수 RSI 높음", "expected_action": "매수", "content": ""}
        existing = [
            {"id": "old", "trigger": "고점매수 RSI 높음", "expected_action": "매수 안 함", "content": ""},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        assert len(conflicts) >= 1
        assert conflicts[0]["conflict_type"] == "contradicting_action"

    def test_no_conflict_same_action(self):
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "VIX 상승", "expected_action": "관망", "content": ""}
        existing = [
            {"id": "old", "trigger": "VIX 상승", "expected_action": "관망", "content": ""},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        for c in conflicts:
            assert c["conflict_type"] != "contradicting_action"

    def test_content_only_lessons(self):
        """Legacy lessons with trigger in content should be detected."""
        from src.data.lesson_conflict import find_conflicts

        new = {"id": "new", "trigger": "고점매수", "expected_action": "RSI 확인", "content": ""}
        existing = [
            {"id": "old", "trigger": "", "expected_action": "",
             "content": "■trigger: 고점매수\n■expected_action: 매수 안 함"},
        ]
        conflicts = find_conflicts(new, existing, similarity_threshold=0.3)
        assert len(conflicts) >= 1

    def test_skips_self(self):
        from src.data.lesson_conflict import find_conflicts

        les = {"id": "same", "trigger": "x", "expected_action": "y", "content": "z"}
        conflicts = find_conflicts(les, [les], similarity_threshold=0.0)
        assert len(conflicts) == 0

    def test_empty_existing(self):
        from src.data.lesson_conflict import find_conflicts
        assert find_conflicts({"trigger": "x"}, []) == []


class TestFindConflictPairs:
    def test_returns_map_with_details(self):
        from src.data.lesson_conflict import find_conflict_pairs

        lessons = [
            {"id": "a", "trigger": "고점매수 RSI", "expected_action": "매수 안 함"},
            {"id": "b", "trigger": "고점매수 RSI", "expected_action": "매수"},
        ]
        result = find_conflict_pairs(lessons)
        assert "a" in result
        assert "b" in result
        assert result["a"].endswith("→ 매수")  # detail 에 상대 lesson 의 action 표시
        assert result["b"].endswith("→ 매수 안 함")

    def test_no_conflict(self):
        from src.data.lesson_conflict import find_conflict_pairs

        lessons = [
            {"id": "a", "trigger": "VIX", "expected_action": "관망"},
            {"id": "b", "trigger": "금리", "expected_action": "채권 매도"},
        ]
        result = find_conflict_pairs(lessons)
        assert len(result) == 0
