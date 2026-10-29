"""src/data/grok_client 테스트 (KIK-359)."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_client import (
    is_available,
    search_x_sentiment,
    _build_sentiment_prompt,
    get_error_status,
    reset_error_state,
)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_with_key(self, monkeypatch):
        """XAI_API_KEY 가 설정되면 True."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        assert is_available() is True

    def test_without_key(self, monkeypatch):
        """XAI_API_KEY 가 없으면 False."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        assert is_available() is False

    def test_empty_key(self, monkeypatch):
        """XAI_API_KEY 가 빈 문자열이면 False."""
        monkeypatch.setenv("XAI_API_KEY", "")
        assert is_available() is False


# ---------------------------------------------------------------------------
# _build_sentiment_prompt
# ---------------------------------------------------------------------------

class TestBuildSentimentPrompt:
    def test_basic_prompt(self):
        """프롬프트에 심볼이 포함된다."""
        prompt = _build_sentiment_prompt("AAPL")
        assert "AAPL" in prompt
        assert "sentiment" in prompt.lower()

    def test_with_company_name(self):
        """프롬프트에 회사명이 포함된다."""
        prompt = _build_sentiment_prompt("005930.KS", "삼성전자")
        assert "삼성전자" in prompt
        assert "005930.KS" in prompt


# ---------------------------------------------------------------------------
# search_x_sentiment
# ---------------------------------------------------------------------------

class TestSearchXSentiment:
    def test_no_api_key(self, monkeypatch):
        """API 키가 없으면 빈 결과를 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_x_sentiment("AAPL")
        assert result["positive"] == []
        assert result["negative"] == []
        assert result["sentiment_score"] == 0.0
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """Grok API 정상 응답을 파싱한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "positive": ["Strong earnings beat", "AI growth momentum"],
            "negative": ["China market weakness"],
            "sentiment_score": 0.6,
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json_content}
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = search_x_sentiment("AAPL", "Apple Inc.")
        assert len(result["positive"]) == 2
        assert len(result["negative"]) == 1
        assert result["sentiment_score"] == 0.6
        assert result["raw_response"] == json_content

    @patch("src.data.grok_client.requests.post")
    def test_api_error(self, mock_post, monkeypatch):
        """API 오류 시 빈 결과를 반환한다(graceful degradation)."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = search_x_sentiment("AAPL")
        assert result["positive"] == []
        assert result["sentiment_score"] == 0.0

    @patch("src.data.grok_client.requests.post")
    def test_timeout(self, mock_post, monkeypatch):
        """타임아웃 시 빈 결과를 반환한다."""
        import requests as req
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.side_effect = req.exceptions.Timeout("Timed out")

        result = search_x_sentiment("AAPL", timeout=1)
        assert result["positive"] == []

    @patch("src.data.grok_client.requests.post")
    def test_malformed_json_response(self, mock_post, monkeypatch):
        """응답의 잘못된 JSON 을 처리한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "This is not JSON at all"}
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = search_x_sentiment("AAPL")
        assert result["raw_response"] == "This is not JSON at all"
        assert result["positive"] == []

    @patch("src.data.grok_client.requests.post")
    def test_sentiment_score_clamping(self, mock_post, monkeypatch):
        """센티먼트 점수는 [-1, 1] 로 클램프된다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "positive": [],
            "negative": [],
            "sentiment_score": 5.0,  # Out of range
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json_content}
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        result = search_x_sentiment("AAPL")
        assert result["sentiment_score"] == 1.0

    @patch("src.data.grok_client.requests.post")
    def test_empty_output(self, mock_post, monkeypatch):
        """API 출력이 없으면 빈 결과를 반환한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"output": []}
        mock_post.return_value = mock_response

        result = search_x_sentiment("AAPL")
        assert result["positive"] == []


# ---------------------------------------------------------------------------
# get_error_status (KIK-431)
# ---------------------------------------------------------------------------

class TestGetErrorStatus:
    """에러 상태 추적 테스트 (KIK-431)."""

    def setup_method(self):
        """각 테스트 전에 에러 상태를 초기화한다."""
        reset_error_state()

    def test_not_configured(self, monkeypatch):
        """XAI_API_KEY 가 없으면 status 는 not_configured."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        search_x_sentiment("AAPL")
        status = get_error_status()
        assert status["status"] == "not_configured"
        assert status["status_code"] is None

    @patch("src.data.grok_client.requests.post")
    def test_auth_error(self, mock_post, monkeypatch):
        """HTTP 401 이면 status 는 auth_error."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        search_x_sentiment("AAPL")
        status = get_error_status()
        assert status["status"] == "auth_error"
        assert status["status_code"] == 401

    @patch("src.data.grok_client.requests.post")
    def test_rate_limited(self, mock_post, monkeypatch):
        """HTTP 429 면 status 는 rate_limited."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        search_x_sentiment("AAPL")
        status = get_error_status()
        assert status["status"] == "rate_limited"
        assert status["status_code"] == 429

    @patch("src.data.grok_client.requests.post")
    def test_other_error(self, mock_post, monkeypatch):
        """200/401/429 외 응답이면 status 는 other_error."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        search_x_sentiment("AAPL")
        status = get_error_status()
        assert status["status"] == "other_error"
        assert status["status_code"] == 500

    @patch("src.data.grok_client.requests.post")
    def test_timeout(self, mock_post, monkeypatch):
        """요청 타임아웃이면 status 는 timeout."""
        import requests as req
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.side_effect = req.exceptions.Timeout("Timed out")

        search_x_sentiment("AAPL", timeout=1)
        status = get_error_status()
        assert status["status"] == "timeout"
        assert status["status_code"] is None

    @patch("src.data.grok_client.requests.post")
    def test_ok(self, mock_post, monkeypatch):
        """호출 성공 시 status 는 ok."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"positive":[],"negative":[],"sentiment_score":0}'}],
                }
            ]
        }
        mock_post.return_value = mock_response

        search_x_sentiment("AAPL")
        status = get_error_status()
        assert status["status"] == "ok"
        assert status["status_code"] == 200

    def test_reset_error_state(self, monkeypatch):
        """reset_error_state() 가 모든 상태 필드를 초기화한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        search_x_sentiment("AAPL")
        assert get_error_status()["status"] == "not_configured"

        reset_error_state()
        status = get_error_status()
        assert status["status"] == "ok"
        assert status["status_code"] is None
        assert status["message"] == ""
