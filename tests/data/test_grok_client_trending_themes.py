"""grok_client get_trending_themes 테스트 (KIK-440)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_client import (
    _build_trending_themes_prompt,
    _parse_json_array_response,
    get_trending_themes,
    EMPTY_TRENDING_THEMES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grok_response(text: str) -> MagicMock:
    """*text* 를 API 출력으로 돌려주는 모의 HTTP 응답을 만든다."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": text}
                ],
            }
        ]
    }
    return mock_response


@pytest.fixture(autouse=True)
def _reset_error_warned():
    from src.data import grok_client
    grok_client._error_warned[0] = False
    yield


# ===================================================================
# _parse_json_array_response
# ===================================================================

class TestParseJsonArrayResponse:
    def test_valid_array(self):
        result = _parse_json_array_response('[{"a": 1}, {"b": 2}]')
        assert len(result) == 2
        assert result[0]["a"] == 1

    def test_array_with_surrounding_text(self):
        result = _parse_json_array_response('Here are results: [{"x": 1}] done.')
        assert len(result) == 1

    def test_empty_array(self):
        result = _parse_json_array_response("[]")
        assert result == []

    def test_not_json(self):
        result = _parse_json_array_response("no json here")
        assert result == []

    def test_object_returns_empty(self):
        result = _parse_json_array_response('{"key": "value"}')
        assert result == []

    def test_malformed_json(self):
        result = _parse_json_array_response("[{broken")
        assert result == []


# ===================================================================
# _build_trending_themes_prompt
# ===================================================================

class TestBuildTrendingThemesPrompt:
    def test_kr(self):
        prompt = _build_trending_themes_prompt("kr")
        assert "한국 시장" in prompt
        assert "ai" in prompt
        assert "defense" in prompt
        assert "JSON" in prompt

    def test_us(self):
        prompt = _build_trending_themes_prompt("us")
        assert "미국 시장" in prompt

    def test_default_is_kr(self):
        """region 생략 시 한국 시장."""
        prompt = _build_trending_themes_prompt()
        assert "한국 시장" in prompt

    def test_unknown_region_falls_back_to_kr(self):
        """제거된 지역(japan/global 등)은 kr 로 폴백한다."""
        for region in ("japan", "jp", "global", "unknown"):
            prompt = _build_trending_themes_prompt(region)
            assert "한국 시장" in prompt, region

    def test_contains_valid_theme_keys(self):
        prompt = _build_trending_themes_prompt("kr")
        for key in ["ai", "ev", "cloud-saas", "cybersecurity", "biotech",
                     "renewable-energy", "fintech", "defense", "healthcare"]:
            assert key in prompt


# ===================================================================
# get_trending_themes
# ===================================================================

class TestGetTrendingThemes:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = get_trending_themes("kr")
        assert result["themes"] == []
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_array_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": "ai", "reason": "반도체 수요 확대", "confidence": 0.9},
            {"theme": "defense", "reason": "지정학 리스크", "confidence": 0.8},
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        assert len(result["themes"]) == 2
        assert result["themes"][0]["theme"] == "ai"
        assert result["themes"][0]["confidence"] == 0.9
        assert result["themes"][0]["reason"] == "반도체 수요 확대"

    @patch("src.data.grok_client.requests.post")
    def test_successful_object_response(self, mock_post, monkeypatch):
        """Grok 이 배열 대신 {themes: [...]} 객체를 반환할 수도 있다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "themes": [
                {"theme": "ev", "reason": "EV sales up", "confidence": 0.7},
            ]
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("us")
        assert len(result["themes"]) == 1
        assert result["themes"][0]["theme"] == "ev"

    @patch("src.data.grok_client.requests.post")
    def test_confidence_sort_descending(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": "biotech", "reason": "r1", "confidence": 0.5},
            {"theme": "ai", "reason": "r2", "confidence": 0.9},
            {"theme": "ev", "reason": "r3", "confidence": 0.7},
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        confs = [t["confidence"] for t in result["themes"]]
        assert confs == [0.9, 0.7, 0.5]

    @patch("src.data.grok_client.requests.post")
    def test_empty_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("")

        result = get_trending_themes("kr")
        assert result["themes"] == []

    @patch("src.data.grok_client.requests.post")
    def test_non_json_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("Not JSON at all")

        result = get_trending_themes("kr")
        assert result["themes"] == []
        assert result["raw_response"] == "Not JSON at all"

    @patch("src.data.grok_client.requests.post")
    def test_unknown_themes_passthrough(self, mock_post, monkeypatch):
        """알 수 없는 테마 키도 그대로 통과시킨다(검증은 스크립트 층에서)."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": "ai", "reason": "r1", "confidence": 0.9},
            {"theme": "quantum-computing", "reason": "r2", "confidence": 0.6},
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        themes = [t["theme"] for t in result["themes"]]
        assert "ai" in themes
        assert "quantum-computing" in themes

    @patch("src.data.grok_client.requests.post")
    def test_theme_key_normalized(self, mock_post, monkeypatch):
        """테마 키는 소문자화·공백 제거된다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": " AI ", "reason": "r1", "confidence": 0.8},
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        assert result["themes"][0]["theme"] == "ai"

    @patch("src.data.grok_client.requests.post")
    def test_malformed_items_filtered(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": "ai", "reason": "ok", "confidence": 0.9},
            {"reason": "missing theme"},
            {"theme": 123, "reason": "bad type"},
            "not a dict",
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        assert len(result["themes"]) == 1
        assert result["themes"][0]["theme"] == "ai"

    @patch("src.data.grok_client.requests.post")
    def test_default_confidence(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = [
            {"theme": "ai", "reason": "r1"},
        ]
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = get_trending_themes("kr")
        assert result["themes"][0]["confidence"] == 0.5

    @patch("src.data.grok_client.requests.post")
    def test_api_error_returns_empty(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        result = get_trending_themes("kr")
        assert result["themes"] == []
