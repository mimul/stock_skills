"""src.data.conviction 테스트 (코드 리뷰 H4: 매도 금지 키워드 SSoT)."""

import pytest

from src.data.conviction import CONVICTION_KEYWORDS, is_conviction_text
from src.data import preflight
from src.data.context import fallback_context


class TestIsConvictionText:
    @pytest.mark.parametrize("content", [
        "홀드확정",
        "홀드 확정 종목",
        "이건 안 팜",
        "절대 안 판다",
        "안 팔 거임",
        "안팔아",
        "팔지 않을 것",
        "매도금지",
        "매도 금지",
        "장기 보유 확정",
        "CONVICTION pick",
    ])
    def test_variants_detected(self, content):
        assert is_conviction_text(content) is True

    @pytest.mark.parametrize("content", ["실적 좋음", "분할 매도 검토", "", "팔았다"])
    def test_plain_text_not_detected(self, content):
        assert is_conviction_text(content) is False

    def test_source_prefix_detected(self):
        assert is_conviction_text("아무 내용", source="user-conviction-2026") is True

    def test_keywords_have_no_whitespace(self):
        """키워드는 공백 제거 본문과 비교하므로 공백을 포함하면 안 된다."""
        assert all(" " not in k for k in CONVICTION_KEYWORDS)


class TestSharedBetweenModules:
    def test_preflight_alias_points_to_ssot(self):
        assert preflight._CONVICTION_KEYWORDS is CONVICTION_KEYWORDS

    def test_fallback_context_uses_same_rule(self):
        notes = [{"content": "이 종목은 절대 안 판다", "source": "user"}]
        assert fallback_context._detect_conviction(notes) == "이 종목은 절대 안 판다"
