"""Grok API (xAI) 래퍼 — X 검색·센티먼트 분석 (KIK-359).

xAI Responses API 로 X(Twitter) 게시물을 검색하고 개별 종목·업종·시장의
투자자 센티먼트를 분석한다.

API 키는 XAI_API_KEY 환경 변수에서 읽는다.
키가 없으면 is_available() 이 False 를 반환하고 모든 검색 함수는
빈 결과를 돌려준다(graceful degradation).

KIK-508 에서 서브모듈로 분할.
"""

# 기존 @patch("src.data.grok_client.requests.post") 가 계속 동작하도록
# `requests` 를 패키지 레벨에서 re-export 한다.
import requests  # noqa: F401

# --- 공용: 상수, 헬퍼, 에러 상태 ---
from src.data.grok_client._common import (  # noqa: F401
    EMPTY_STOCK_DEEP,
    EMPTY_INDUSTRY,
    EMPTY_MARKET,
    EMPTY_TRENDING,
    EMPTY_BUSINESS,
    EMPTY_TRENDING_THEMES,
    is_available,
    get_error_status,
    reset_error_state,
    # 테스트 호환을 위해 re-export 하는 비공개 헬퍼
    _get_api_key,
    _is_korean_stock,
    _contains_korean,
    _call_grok_api,
    _parse_json_response,
    _parse_json_array_response,
    _error_warned,
    _error_state,
    _API_URL,
    _DEFAULT_MODEL,
)

# --- 종목 함수 ---
from src.data.grok_client.stock import (  # noqa: F401
    search_x_sentiment,
    search_stock_deep,
    _build_sentiment_prompt,
    _build_stock_deep_prompt,
)

# --- 시장 함수 ---
from src.data.grok_client.market import (  # noqa: F401
    search_market,
    search_trending_stocks,
    get_trending_themes,
    _build_trending_prompt,
    _build_market_prompt,
    _build_trending_themes_prompt,
)

# --- 업종 함수 ---
from src.data.grok_client.industry import (  # noqa: F401
    search_industry,
    _build_industry_prompt,
)

# --- 비즈니스 모델 함수 ---
from src.data.grok_client.business import (  # noqa: F401
    search_business,
    synthesize_text,
    _build_business_prompt,
)
