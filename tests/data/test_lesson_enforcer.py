"""Tests for src.data.lesson_enforcer (KIK-736)."""

from __future__ import annotations

import pytest

from src.data.lesson_enforcer import (
    filter_relevant_lessons,
    verify_lesson_cited,
)


# ---------------------------------------------------------------------------
# filter_relevant_lessons
# ---------------------------------------------------------------------------


class TestFilterRelevantLessons:
    def test_matches_trigger_token(self):
        lessons = [
            {"id": "L1", "trigger": "PF 전체 리뷰 / 철저", "content": "..."},
            {"id": "L2", "trigger": "실적 분석", "content": "..."},
        ]
        result = filter_relevant_lessons("포트폴리오를 철저하게 재점검하고 싶어", lessons)
        assert any(l["id"] == "L1" for l in result)
        assert not any(l["id"] == "L2" for l in result)

    def test_ascii_period_split(self):
        """한국어 trigger 는 "."로 끝나므로 ASCII 문장부호도 분리해야 한다 (코드 리뷰 M4)."""
        lessons = [{"id": "L1", "trigger": "기준일 확인.", "content": "..."}]
        result = filter_relevant_lessons("반도체 주가 확인", lessons)
        assert [l["id"] for l in result] == ["L1"]

    def test_empty_trigger_excluded(self):
        lessons = [
            {"id": "L1", "trigger": "", "content": "general"},
            {"id": "L2", "trigger": "AB", "content": "..."},  # 2글자, user 입력에 미포함
        ]
        result = filter_relevant_lessons("CDE 어때?", lessons)
        assert result == []

    def test_no_user_input_returns_empty(self):
        lessons = [{"id": "L1", "trigger": "PF 전체 리뷰"}]
        assert filter_relevant_lessons("", lessons) == []

    def test_no_lessons_returns_empty(self):
        assert filter_relevant_lessons("철저 리뷰", []) == []

    def test_two_char_token_matches(self):
        # 2글자 토큰도 허용 ("PF"/"주식" 등 짧은 한국어 어휘 대응)
        lessons = [{"id": "L1", "trigger": "PF / 주식"}]
        result = filter_relevant_lessons("PF 주식 재점검", lessons)
        assert any(l["id"] == "L1" for l in result)

    def test_single_char_token_filtered(self):
        # 1글자 토큰은 무시
        lessons = [{"id": "L1", "trigger": "X / Y"}]
        assert filter_relevant_lessons("X Y", lessons) == []

    def test_punctuation_split(self):
        lessons = [{"id": "L1", "trigger": "포트폴리오, 철저 리뷰"}]
        result = filter_relevant_lessons("포트폴리오를 보고 싶어", lessons)
        assert any(l["id"] == "L1" for l in result)


# ---------------------------------------------------------------------------
# verify_lesson_cited
# ---------------------------------------------------------------------------


class TestVerifyLessonCited:
    def test_passes_when_keyphrase_present(self):
        lessons = [
            {"id": "L1",
             "expected_action": "assert_pf_complete 를 추천 생성 전에 통과시킨다",
             "key_kpis": ["Cash% = 15-20%"]},
        ]
        text = "추천 생성 전에 assert_pf_complete 를 통과시킬 것"
        ok, missing = verify_lesson_cited(text, lessons)
        assert ok is True
        assert missing == []

    def test_fails_when_no_keyphrase(self):
        lessons = [
            {"id": "L1",
             "expected_action": "PF 밸런스 normal: Cash 15-20% 를 유지한다",
             "key_kpis": []},
        ]
        text = "완전히 다른 내용을 썼다"
        ok, missing = verify_lesson_cited(text, lessons)
        assert ok is False
        assert "L1" in missing

    def test_no_extractable_phrases_treated_as_cited(self):
        # expected_action 이 짧음 + key_kpis 없음 + content 없음 → 검증 스킵
        lessons = [
            {"id": "L1", "expected_action": "X", "key_kpis": [], "content": ""},
        ]
        ok, missing = verify_lesson_cited("anything", lessons)
        assert ok is True
        assert missing == []

    def test_falls_back_to_content_first_line(self):
        lessons = [
            {"id": "L1",
             "content": "[홀드확정 4/25] NAVER는 팔지 않는다\n이하 계속..."},
        ]
        ok, _ = verify_lesson_cited(
            "[홀드확정 4/25] NAVER는 팔지 않는다 를 준수", lessons
        )
        assert ok is True

    def test_partial_token_match(self):
        # 8글자 이상 토큰이면 폴백으로 일치
        lessons = [
            {"id": "L1",
             "expected_action": "투자판단멀티에이전트시스템 을 활용"},
        ]
        text = "결과에 투자판단멀티에이전트 를 반영"
        ok, _ = verify_lesson_cited(text, lessons)
        assert ok is True

    def test_empty_lessons_passes(self):
        ok, missing = verify_lesson_cited("anything", [])
        assert ok is True
        assert missing == []


# ---------------------------------------------------------------------------
# KIK-738 hook integration scenarios
# Simulate the DeepThink Step 5 verification flow.
# ---------------------------------------------------------------------------


class TestStep5HookScenarios:
    """Simulate META-style mistakes — proposal references a stock that
    a lesson explicitly tells us to avoid, but never quotes the lesson's
    expected_action. verify_lesson_cited must catch this."""

    def test_meta_style_uncited_lesson_fails(self):
        lessons = [{
            "id": "L_DR_CHERRY_PICK",
            "trigger": "Deep Research 결과를 바탕으로 제안을 작성하는 장면",
            "expected_action": "DR 미채택 종목을 plan 에 섞지 않는다",
            "key_kpis": ["DR 미채택 리스트", "cross-check"],
        }]
        # Plan mentions META but never quotes the lesson rule
        proposal = "추천 액션: META +2주 를 신규 편입한다. 이유는 저평가"
        ok, missing = verify_lesson_cited(proposal, lessons)
        assert ok is False
        assert missing == ["L_DR_CHERRY_PICK"]

    def test_proper_citation_passes(self):
        lessons = [{
            "id": "L_ATH",
            "trigger": "신규 매수 후보를 제안하는 장면",
            "expected_action": "52H 로부터의 거리를 반드시 확인",
            "key_kpis": ["52주 고점으로부터의 거리"],
        }]
        proposal = (
            "추천: AVGO 는 52H 로부터의 거리 0.0% 로 ATH 근접. "
            "52H 로부터의 거리를 반드시 확인한 결과, 시험 매수 사이즈로 축소"
        )
        ok, missing = verify_lesson_cited(proposal, lessons)
        assert ok is True

    def test_filter_then_verify_pipeline(self):
        """Simulates Step 1 (filter) → Step 5 (verify) full pipeline.

        trigger 는 filter 용으로 슬래시 구분 복수 토큰 형태라는 전제
        (KIK-738 backfill prompt 가 이 형식으로 추출한다).
        """
        all_lessons = [
            {"id": "L1", "trigger": "신규매수 / 후보제안",
             "expected_action": "52H로부터의 거리를 반드시 확인"},
            {"id": "L2", "trigger": "매도 / 타이밍검토",
             "expected_action": "ATH-40% 에서 +30% 랠리 시 익절"},
        ]
        user_input = "신규매수 후보제안을 검토하고 싶어"
        relevant = filter_relevant_lessons(user_input, all_lessons)
        assert any(l["id"] == "L1" for l in relevant)
        assert all(l["id"] != "L2" for l in relevant)  # L2 is unrelated
        # Proposal must reference the lesson's expected_action keyphrase
        proposal = "신규 후보X 52H로부터의 거리를 반드시 확인한 결과, 시험 매수로 축소"
        ok, _ = verify_lesson_cited(proposal, relevant)
        assert ok is True
