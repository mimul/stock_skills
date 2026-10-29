"""Tests for KIK-571 lesson community classification."""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


@pytest.fixture(autouse=True)
def reset_driver():
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


class TestClassifyLesson:
    def test_bias_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("AI의 보수 편향을 감안한다", "편향") == "판단편향"

    def test_trade_rule_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("펀더멘털 양호해도 -15%에서 손절", "손절 규칙") == "매매규칙"

    def test_macro_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("원유 상승 헤지로 ETF 로테이션", "") == "매크로전략"

    def test_unknown_classification(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("완전히 관계없는 텍스트", "") == "기타"

    def test_empty_input(self):
        from src.data.lesson_community import classify_lesson
        assert classify_lesson("", "") == "기타"

    def test_mixed_keywords(self):
        from src.data.lesson_community import classify_lesson
        # RSI is a sell rule keyword
        result = classify_lesson("RSI 높을 때 진입 조건", "진입 규칙")
        assert result == "매매규칙"


class TestInferThemeFromInput:
    def test_market_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("시황 체크") == "매크로전략"

    def test_health_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("헬스체크") == "매매규칙"

    def test_bias_query(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("판단 편향에 주의") == "판단편향"

    def test_no_match(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("안녕하세요") is None

    def test_empty(self):
        from src.data.lesson_community import infer_theme_from_input
        assert infer_theme_from_input("") is None


class TestMergeLessonCommunity:
    def test_merge_creates_node(self):
        from src.data.lesson_community import merge_lesson_community
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        gs._driver = driver

        with patch("src.data.graph_store._get_mode", return_value="full"):
            result = merge_lesson_community("note_001", "매매규칙")

        assert result is True
        assert session.run.call_count == 2  # MERGE node + MERGE rel

    def test_mode_off(self):
        from src.data.lesson_community import merge_lesson_community

        with patch("src.data.graph_store._get_mode", return_value="off"):
            assert merge_lesson_community("note_001", "test") is False


class TestGetLessonsByTheme:
    def test_returns_lessons(self):
        from src.data.lesson_community import get_lessons_by_theme
        import src.data.graph_store as gs

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        r1 = MagicMock()
        r1.keys = lambda: ["id", "content", "trigger", "expected_action", "date"]
        r1.__getitem__ = lambda s, k: {
            "id": "n1", "content": "손절 규칙",
            "trigger": "펀더멘털 양호해도", "expected_action": "-15%에서 손절",
            "date": "2026-03-20",
        }[k]
        session.run.return_value = iter([r1])
        gs._driver = driver

        result = get_lessons_by_theme("매매규칙")
        assert len(result) == 1
        assert result[0]["trigger"] == "펀더멘털 양호해도"

    def test_no_driver(self):
        from src.data.lesson_community import get_lessons_by_theme
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert get_lessons_by_theme("test") == []


class TestSaveNoteIntegration:
    def test_lesson_gets_community(self, tmp_path):
        from src.data.note_manager import save_note

        with patch("src.data.lesson_community.merge_lesson_community", return_value=True) as mock_merge:
            note = save_note(
                note_type="lesson",
                content="손절은 -15%",
                trigger="펀더멘털 양호해도 손절",
                expected_action="-15%에서 철수",
                base_dir=str(tmp_path),
            )

        assert note.get("_lesson_community") == "매매규칙"
        mock_merge.assert_called_once()
