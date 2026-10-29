"""grok_client 리서치 함수 테스트 (KIK-367).

_call_grok_api, _parse_json_response, _is_korean_stock, _contains_korean,
search_stock_deep, search_industry, search_market, search_business 를 검증한다.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_client import (
    _call_grok_api,
    _parse_json_response,
    _is_korean_stock,
    _contains_korean,
    search_stock_deep,
    search_industry,
    search_market,
    search_business,
    EMPTY_STOCK_DEEP,
    EMPTY_INDUSTRY,
    EMPTY_MARKET,
    EMPTY_BUSINESS,
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
    """각 테스트 전에 모듈 레벨 _error_warned 플래그를 초기화한다."""
    from src.data import grok_client
    grok_client._error_warned[0] = False
    yield


# ===================================================================
# _call_grok_api
# ===================================================================

class TestCallGrokApi:

    def test_no_api_key(self, monkeypatch):
        """XAI_API_KEY 가 없으면 빈 문자열을 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = _call_grok_api("test prompt")
        assert result == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """정상 응답의 텍스트 내용을 반환한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("Hello from Grok")

        result = _call_grok_api("test prompt")
        assert result == "Hello from Grok"

    @patch("src.data.grok_client.requests.post")
    def test_api_error(self, mock_post, monkeypatch):
        """HTTP 500 이면 빈 문자열을 반환한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = _call_grok_api("test prompt")
        assert result == ""

    @patch("src.data.grok_client.requests.post")
    def test_timeout(self, mock_post, monkeypatch):
        """타임아웃 시 빈 문자열을 반환한다."""
        import requests as req
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.side_effect = req.exceptions.Timeout("Timed out")

        result = _call_grok_api("test prompt", timeout=1)
        assert result == ""

    @patch("src.data.grok_client.requests.post")
    def test_request_exception(self, mock_post, monkeypatch):
        """일반 요청 예외 시 빈 문자열을 반환한다."""
        import requests as req
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        result = _call_grok_api("test prompt")
        assert result == ""


# ===================================================================
# _parse_json_response
# ===================================================================

class TestParseJsonResponse:

    def test_valid_json(self):
        """순수 JSON 문자열을 파싱한다."""
        text = '{"key": "value", "count": 42}'
        result = _parse_json_response(text)
        assert result == {"key": "value", "count": 42}

    def test_json_with_surrounding_text(self):
        """앞뒤 텍스트가 있어도 JSON 을 추출한다."""
        text = 'Here is the result: {"key": "value"} and more text'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        """유효한 JSON 이 없으면 빈 dict 를 반환한다."""
        result = _parse_json_response("This is just plain text")
        assert result == {}

    def test_empty_string(self):
        """빈 문자열이면 빈 dict 를 반환한다."""
        result = _parse_json_response("")
        assert result == {}


# ===================================================================
# _is_korean_stock
# ===================================================================

class TestIsKoreanStock:

    def test_ks_suffix(self):
        """005930.KS 는 한국(KOSPI) 종목."""
        assert _is_korean_stock("005930.KS") is True

    def test_kq_suffix(self):
        """247540.KQ 는 한국(KOSDAQ) 종목."""
        assert _is_korean_stock("247540.KQ") is True

    def test_lowercase_suffix(self):
        """소문자 접미사도 한국 종목으로 인식한다."""
        assert _is_korean_stock("005930.ks") is True

    def test_us_stock(self):
        """AAPL 은 한국 종목이 아니다."""
        assert _is_korean_stock("AAPL") is False

    def test_cash_symbol(self):
        """KRW.CASH 는 종목이 아니다."""
        assert _is_korean_stock("KRW.CASH") is False


# ===================================================================
# _contains_korean
# ===================================================================

class TestContainsKorean:

    def test_korean_text(self):
        """한글 텍스트는 True."""
        assert _contains_korean("반도체") is True

    def test_english_text(self):
        """영문만 있으면 False."""
        assert _contains_korean("semiconductor") is False

    def test_mixed(self):
        """영문·한글 혼합 텍스트는 True."""
        assert _contains_korean("AI반도체") is True

    def test_jamo(self):
        """호환 자모(ㄱ 등)도 한글로 본다."""
        assert _contains_korean("ㄱㄴㄷ") is True

    def test_empty(self):
        """빈 문자열은 False."""
        assert _contains_korean("") is False


# ===================================================================
# search_stock_deep
# ===================================================================

class TestSearchStockDeep:

    def test_no_api_key(self, monkeypatch):
        """API 키가 없으면 EMPTY_STOCK_DEEP 을 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_stock_deep("AAPL")
        assert result["recent_news"] == []
        assert result["catalysts"] == {"positive": [], "negative": []}
        assert result["x_sentiment"]["score"] == 0.0
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """심층 리서치 정상 응답을 파싱한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "recent_news": ["Earnings beat expectations", "New product launch"],
            "catalysts": {
                "positive": ["AI revenue growth"],
                "negative": ["Trade war risk"],
            },
            "analyst_views": ["Buy rating from Goldman"],
            "x_sentiment": {
                "score": 0.7,
                "summary": "Bullish sentiment",
                "key_opinions": ["Strong buy signals"],
            },
            "competitive_notes": ["Market leader in segment"],
        })

        mock_post.return_value = _make_grok_response(json_content)

        result = search_stock_deep("AAPL", "Apple Inc.")
        assert len(result["recent_news"]) == 2
        assert result["catalysts"]["positive"] == ["AI revenue growth"]
        assert result["catalysts"]["negative"] == ["Trade war risk"]
        assert result["analyst_views"] == ["Buy rating from Goldman"]
        assert result["x_sentiment"]["score"] == 0.7
        assert result["x_sentiment"]["summary"] == "Bullish sentiment"
        assert result["competitive_notes"] == ["Market leader in segment"]

    @patch("src.data.grok_client.requests.post")
    def test_korean_stock_prompt(self, mock_post, monkeypatch):
        """한국 종목(005930.KS)은 한국어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_stock_deep("005930.KS", "Samsung Electronics")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "005930.KS" in prompt
        assert "조사해 주세요" in prompt
        assert "Research" not in prompt
        # JSON 응답 키는 영어 그대로 유지
        assert '"recent_news"' in prompt
        assert '"x_sentiment"' in prompt

    @patch("src.data.grok_client.requests.post")
    def test_korean_company_name_prompt(self, mock_post, monkeypatch):
        """미국 티커라도 회사명에 한글이 있으면 한국어 프롬프트."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_stock_deep("AAPL", "애플")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "조사해 주세요" in prompt

    @patch("src.data.grok_client.requests.post")
    def test_us_stock_prompt(self, mock_post, monkeypatch):
        """미국 종목(AAPL)은 영어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_stock_deep("AAPL", "Apple Inc.")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "Research" in prompt
        assert "조사" not in prompt

    @patch("src.data.grok_client.requests.post")
    def test_malformed_response(self, mock_post, monkeypatch):
        """잘못된 JSON 이면 raw_response 만 채우고 데이터는 비워 둔다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("This is not JSON at all")

        result = search_stock_deep("AAPL")
        assert result["raw_response"] == "This is not JSON at all"
        assert result["recent_news"] == []
        assert result["catalysts"] == {"positive": [], "negative": []}


# ===================================================================
# search_industry
# ===================================================================

class TestSearchIndustry:

    def test_no_api_key(self, monkeypatch):
        """API 키가 없으면 EMPTY_INDUSTRY 를 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_industry("반도체")
        assert result["trends"] == []
        assert result["key_players"] == []
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """업종 리서치 정상 응답을 파싱한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "trends": ["AI chip demand surging"],
            "key_players": [
                {"name": "TSMC", "ticker": "TSM", "note": "Foundry leader"}
            ],
            "growth_drivers": ["Data center expansion"],
            "risks": ["Geopolitical tension"],
            "regulatory": ["US export controls"],
            "investor_focus": ["CAPEX cycle"],
        })

        mock_post.return_value = _make_grok_response(json_content)

        result = search_industry("semiconductor")
        assert result["trends"] == ["AI chip demand surging"]
        assert len(result["key_players"]) == 1
        assert result["key_players"][0]["name"] == "TSMC"
        assert result["growth_drivers"] == ["Data center expansion"]
        assert result["risks"] == ["Geopolitical tension"]
        assert result["regulatory"] == ["US export controls"]
        assert result["investor_focus"] == ["CAPEX cycle"]

    @patch("src.data.grok_client.requests.post")
    def test_korean_theme(self, mock_post, monkeypatch):
        """한글 테마는 한국어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_industry("반도체")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "반도체" in prompt
        assert "업종" in prompt
        assert "Research" not in prompt

    @patch("src.data.grok_client.requests.post")
    def test_english_theme(self, mock_post, monkeypatch):
        """영문 테마는 영어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_industry("semiconductor")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "Research" in prompt


# ===================================================================
# search_market
# ===================================================================

class TestSearchMarket:

    def test_no_api_key(self, monkeypatch):
        """API 키가 없으면 EMPTY_MARKET 을 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_market("KOSPI")
        assert result["price_action"] == ""
        assert result["macro_factors"] == []
        assert result["sentiment"]["score"] == 0.0
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """시장 리서치 정상 응답을 파싱한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "price_action": "KOSPI rose 1.5% on strong earnings",
            "macro_factors": ["BOK rate decision", "Won weakness"],
            "sentiment": {"score": 0.4, "summary": "Cautiously optimistic"},
            "upcoming_events": ["GDP release on Friday"],
            "sector_rotation": ["From defensive to cyclical"],
        })

        mock_post.return_value = _make_grok_response(json_content)

        result = search_market("KOSPI")
        assert result["price_action"] == "KOSPI rose 1.5% on strong earnings"
        assert len(result["macro_factors"]) == 2
        assert result["sentiment"]["score"] == 0.4
        assert result["sentiment"]["summary"] == "Cautiously optimistic"
        assert result["upcoming_events"] == ["GDP release on Friday"]
        assert result["sector_rotation"] == ["From defensive to cyclical"]

    @patch("src.data.grok_client.requests.post")
    def test_market_prompt_is_korean(self, mock_post, monkeypatch):
        """시장 프롬프트는 입력과 무관하게 한국어이며 JSON 키는 유지된다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_market("S&P500")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "S&P500" in prompt
        assert "시장 개황" in prompt
        assert '"price_action"' in prompt
        assert '"sector_rotation"' in prompt


# ===================================================================
# search_business
# ===================================================================

class TestSearchBusiness:

    def test_no_api_key(self, monkeypatch):
        """API 키가 없으면 EMPTY_BUSINESS 를 반환한다."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = search_business("035420.KS")
        assert result["overview"] == ""
        assert result["segments"] == []
        assert result["revenue_model"] == ""
        assert result["competitive_advantages"] == []
        assert result["raw_response"] == ""

    @patch("src.data.grok_client.requests.post")
    def test_successful_response(self, mock_post, monkeypatch):
        """비즈니스 모델 정상 응답을 파싱한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "overview": "NAVER is Korea's leading search and internet platform company",
            "segments": [
                {"name": "Search Platform", "revenue_share": "55%", "description": "Search ads and display ads"},
                {"name": "Commerce", "revenue_share": "20%", "description": "Smart Store and brand store"},
            ],
            "revenue_model": "Advertising + commerce commission recurring revenue",
            "competitive_advantages": ["Dominant domestic search share", "Platform ecosystem"],
            "key_metrics": ["Search ad growth", "Commerce GMV"],
            "growth_strategy": ["AI (HyperCLOVA X) expansion", "Webtoon global growth"],
            "risks": ["Regulatory pressure on platforms", "Competition from global big tech"],
        })

        mock_post.return_value = _make_grok_response(json_content)

        result = search_business("035420.KS", "NAVER")
        assert result["overview"] == "NAVER is Korea's leading search and internet platform company"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["name"] == "Search Platform"
        assert result["segments"][0]["revenue_share"] == "55%"
        assert result["revenue_model"] == "Advertising + commerce commission recurring revenue"
        assert len(result["competitive_advantages"]) == 2
        assert len(result["key_metrics"]) == 2
        assert len(result["growth_strategy"]) == 2
        assert len(result["risks"]) == 2

    @patch("src.data.grok_client.requests.post")
    def test_korean_stock_prompt(self, mock_post, monkeypatch):
        """한국 종목(035420.KS)은 한국어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_business("035420.KS", "NAVER")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "비즈니스 모델" in prompt
        assert "Analyze" not in prompt
        assert '"revenue_model"' in prompt

    @patch("src.data.grok_client.requests.post")
    def test_korean_company_name_prompt(self, mock_post, monkeypatch):
        """회사명에 한글이 있으면 한국어 프롬프트."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_business("AAPL", "애플")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "비즈니스 모델" in prompt

    @patch("src.data.grok_client.requests.post")
    def test_us_stock_prompt(self, mock_post, monkeypatch):
        """미국 종목(AAPL)은 영어 프롬프트를 사용한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_business("AAPL", "Apple Inc.")

        prompt = mock_post.call_args[1]["json"]["input"]
        assert "business model" in prompt.lower()
        assert "비즈니스" not in prompt

    @patch("src.data.grok_client.requests.post")
    def test_malformed_response(self, mock_post, monkeypatch):
        """잘못된 JSON 이면 raw_response 만 채우고 데이터는 비워 둔다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("This is not JSON at all")

        result = search_business("035420.KS")
        assert result["raw_response"] == "This is not JSON at all"
        assert result["overview"] == ""
        assert result["segments"] == []

    @patch("src.data.grok_client.requests.post")
    def test_segment_validation(self, mock_post, monkeypatch):
        """필드가 빠진 세그먼트는 기본값으로 채운다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        json_content = json.dumps({
            "segments": [
                {"name": "Division A"},
                {"name": "Division B", "revenue_share": "30%", "description": "B desc"},
            ],
        })
        mock_post.return_value = _make_grok_response(json_content)

        result = search_business("TEST")
        assert len(result["segments"]) == 2
        assert result["segments"][0]["name"] == "Division A"
        assert result["segments"][0]["revenue_share"] == ""
        assert result["segments"][1]["description"] == "B desc"


# ===================================================================
# Context injection (KIK-488)
# ===================================================================

class TestContextInjection:
    """context 인자가 Grok API 프롬프트에 포함되는지 검증한다."""

    @patch("src.data.grok_client.requests.post")
    def test_stock_deep_context_in_prompt(self, mock_post, monkeypatch):
        """search_stock_deep 이 context 를 프롬프트에 전달한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        ctx = "[INVESTOR CONTEXT]\n- Status: Currently held"
        search_stock_deep("NVDA", "NVIDIA Corp", context=ctx)

        payload = mock_post.call_args[1]["json"]
        assert "[INVESTOR CONTEXT]" in payload["input"]
        assert "Currently held" in payload["input"]

    @patch("src.data.grok_client.requests.post")
    def test_stock_deep_empty_context(self, mock_post, monkeypatch):
        """context 가 비어 있으면 컨텍스트 블록을 넣지 않는다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        search_stock_deep("NVDA", "NVIDIA Corp", context="")

        payload = mock_post.call_args[1]["json"]
        assert "[INVESTOR CONTEXT]" not in payload["input"]

    @patch("src.data.grok_client.requests.post")
    def test_sentiment_context_in_prompt(self, mock_post, monkeypatch):
        """search_x_sentiment 가 context 를 프롬프트에 전달한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        from src.data.grok_client import search_x_sentiment
        ctx = "[INVESTOR CONTEXT]\n- Thesis: AI leader"
        search_x_sentiment("NVDA", "NVIDIA Corp", context=ctx)

        payload = mock_post.call_args[1]["json"]
        assert "AI leader" in payload["input"]

    @patch("src.data.grok_client.requests.post")
    def test_industry_context_in_prompt(self, mock_post, monkeypatch):
        """search_industry 가 context 를 프롬프트에 전달한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        ctx = "[INVESTOR CONTEXT]\n- Investor holds: NVDA, AVGO"
        search_industry("semiconductor", context=ctx)

        payload = mock_post.call_args[1]["json"]
        assert "NVDA, AVGO" in payload["input"]

    @patch("src.data.grok_client.requests.post")
    def test_market_context_in_prompt(self, mock_post, monkeypatch):
        """search_market 이 context 를 프롬프트에 전달한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        ctx = "[INVESTOR CONTEXT]\n- Portfolio sectors: Technology(3)"
        search_market("S&P500", context=ctx)

        payload = mock_post.call_args[1]["json"]
        assert "Technology(3)" in payload["input"]

    @patch("src.data.grok_client.requests.post")
    def test_business_context_in_prompt(self, mock_post, monkeypatch):
        """search_business 가 context 를 프롬프트에 전달한다."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        mock_post.return_value = _make_grok_response("{}")

        ctx = "[INVESTOR CONTEXT]\n- Status: Currently held"
        search_business("AAPL", "Apple Inc.", context=ctx)

        payload = mock_post.call_args[1]["json"]
        assert "Currently held" in payload["input"]
