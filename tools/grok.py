"""Grok API Tool — Grok (xAI) 검색 파사드.

tools/ 층은 API 호출만 담당한다. 판단 로직은 포함하지 않는다.
src/data/grok_client/ 의 순수 검색 함수를 re-export 한다.
XAI_API_KEY 미설정 시 graceful degradation(각 함수가 빈 값을 반환).
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from src.data.grok_client import (  # noqa: E402
        # 가용성 체크
        is_available,
        get_error_status,
        # 종목 검색
        search_stock_deep,
        search_x_sentiment,
        # 시장 검색
        search_market,
        search_trending_stocks,
        get_trending_themes,
        # 업종 검색
        search_industry,
        # 비즈니스 모델 검색
        search_business,
        # 텍스트 합성
        synthesize_text,
    )
    # KIK-732: 벌크 검색 래퍼 (DeepThink Step 3 용)
    from src.data.grok_client.bulk_search import (  # noqa: E402
        bulk_x_search,
        bulk_web_search,
    )
    HAS_GROK = True
except ImportError:
    HAS_GROK = False

__all__ = [
    # 가용성
    "is_available",
    "get_error_status",
    # 종목
    "search_stock_deep",
    "search_x_sentiment",
    # 시장
    "search_market",
    "search_trending_stocks",
    "get_trending_themes",
    # 업종
    "search_industry",
    # 비즈니스 모델
    "search_business",
    # 텍스트 합성
    "synthesize_text",
    # KIK-732: 벌크 검색
    "bulk_x_search",
    "bulk_web_search",
    # 플래그
    "HAS_GROK",
]
