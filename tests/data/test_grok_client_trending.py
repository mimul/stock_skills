"""grok_client 트렌딩 종목 검색 테스트 (KIK-370)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_client import (
    _build_trending_prompt,
    search_trending_stocks,
    EMPTY_TRENDING,
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
# _build_trending_prompt
# ===================================================================

class TestBuildTrendingPrompt:
    def test_kr_default(self):
        """region 생략 시 한국(kr) 한국어 프롬프트."""
        prompt = _build_trending_prompt()
        assert "한국 주식" in prompt
        assert ".KS/.KQ" in prompt
        assert "005930.KS" in prompt
        assert "JSON" in prompt

    def test_kr_region(self):
        """kr 은 한국어 프롬프트 + KOSPI/KOSDAQ 접미사 안내."""
        prompt = _build_trending_prompt("kr")
        assert "한국 주식" in prompt
        assert "KOSDAQ uses .KQ" in prompt
        assert "Search X (Twitter)" not in prompt

    def test_us_region(self):
        """us 는 영어 프롬프트 + 접미사 없는 티커 예시."""
        prompt = _build_trending_prompt("us")
        assert "US stock exchanges" in prompt
        assert "AAPL" in prompt
        assert ".KS" not in prompt
        assert "한국 주식" not in prompt

    def test_with_theme(self):
        prompt = _build_trending_prompt("kr", theme="AI")
        assert "AI" in prompt

    def test_without_theme(self):
        prompt = _build_trending_prompt("kr", theme=None)
        assert "Focus specifically" not in prompt

    def test_unknown_region_falls_back_to_kr(self):
        """알 수 없는 region(jp 등 제거된 지역 포함)은 kr 로 폴백한다."""
        for region in ("unknown", "jp", "japan", "asean", "hk"):
            prompt = _build_trending_prompt(region)
            assert "한국 주식" in prompt, region

    def test_region_aliases_normalized(self):
        """대소문자·한글 별칭을 kr/us 로 정규화한다 (코드 리뷰 M6)."""
        from src.data.grok_client.market import normalize_region
        assert normalize_region("US") == "us"
        assert normalize_region(" usa ") == "us"
        assert normalize_region("미국") == "us"
        assert normalize_region("한국") == "kr"
        assert normalize_region(None) == "kr"
        assert normalize_region("japan") == "kr"

    def test_us_prompt_has_no_korean_label(self):
        prompt = _build_trending_prompt("미국")
        assert "US stocks" in prompt
        assert "미국 주식" not in prompt

    def test_no_japan_mentions(self):
        """일본 시장 언급이 프롬프트에 남아 있지 않다."""
        for region in ("kr", "us"):
            prompt = _build_trending_prompt(region)
            assert "Tokyo" not in prompt
            assert "Toyota" not in prompt


# ===================================================================
# search_trending_stocks
# ===================================================================

class TestSearchTrendingStocks:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_trending_stocks("kr")
        assert result["stocks"] == []
        assert result["market_context"] == ""
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [
                {"ticker": "005930.KS", "name": "삼성전자", "reason": "HBM investment"},
                {"ticker": "000660.KS", "name": "SK하이닉스", "reason": "AI memory demand"},
            ],
            "market_context": "Bullish on Korean semiconductors",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("kr")
        assert len(result["stocks"]) == 2
        assert result["stocks"][0]["ticker"] == "005930.KS"
        assert result["stocks"][0]["name"] == "삼성전자"
        assert result["stocks"][0]["reason"] == "HBM investment"
        assert result["market_context"] == "Bullish on Korean semiconductors"

    @patch("src.data.grok_client.requests.post")
    def test_malformed_stocks_filtered(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [
                {"ticker": "005930.KS", "name": "삼성전자", "reason": "OK"},
                {"name": "No Ticker Corp", "reason": "missing"},
                {"ticker": 123, "name": "Bad type"},
            ],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("kr")
        assert len(result["stocks"]) == 1
        assert result["stocks"][0]["ticker"] == "005930.KS"

    @patch("src.data.grok_client.requests.post")
    def test_theme_in_prompt(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response('{"stocks": [], "market_context": ""}')

        search_trending_stocks("us", theme="AI")

        call_args = mock_post.call_args
        prompt = call_args[1]["json"]["input"]
        assert "AI" in prompt

    @patch("src.data.grok_client.requests.post")
    def test_api_error_returns_empty(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        result = search_trending_stocks("kr")
        assert result["stocks"] == []

    @patch("src.data.grok_client.requests.post")
    def test_non_json_response(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("Not JSON at all")

        result = search_trending_stocks("kr")
        assert result["stocks"] == []
        assert result["raw_response"] == "Not JSON at all"

    @patch("src.data.grok_client.requests.post")
    def test_empty_stocks_list(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response(
            '{"stocks": [], "market_context": "No trends"}'
        )

        result = search_trending_stocks("kr")
        assert result["stocks"] == []
        assert result["market_context"] == "No trends"

    @patch("src.data.grok_client.requests.post")
    def test_ticker_whitespace_stripped(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [{"ticker": " 005930.KS ", "name": "삼성전자", "reason": "test"}],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("kr")
        assert result["stocks"][0]["ticker"] == "005930.KS"

    @patch("src.data.grok_client.requests.post")
    def test_non_string_name_reason(self, mock_post, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        payload = {
            "stocks": [{"ticker": "AAPL", "name": 123, "reason": None}],
            "market_context": "",
        }
        mock_post.return_value = _make_grok_response(json.dumps(payload))

        result = search_trending_stocks("us")
        assert result["stocks"][0]["name"] == ""
        assert result["stocks"][0]["reason"] == ""
