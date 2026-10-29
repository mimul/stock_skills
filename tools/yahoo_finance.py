"""Yahoo Finance Tool — 데이터 조회 파사드.

tools/ 층은 외부 API 접속만 담당한다. 판단 로직(스코어 계산, 필터링 등)은 포함하지 않는다.
src/data/yahoo_client/ 의 순수 데이터 조회 함수를 re-export 한다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.yahoo_client import (  # noqa: E402
    get_stock_info,
    get_multiple_stocks,
    get_stock_detail,
    get_price_history,
    get_stock_news,
    get_macro_indicators,
    screen_stocks,
    get_sector_rs,
    SECTOR_ETFS,
)
from src.data.kr_valuation import get_valuation as get_kr_valuation  # noqa: E402

__all__ = [
    "get_stock_info",
    "get_multiple_stocks",
    "get_stock_detail",
    "get_price_history",
    "get_stock_news",
    "get_macro_indicators",
    "screen_stocks",
    "get_sector_rs",
    "SECTOR_ETFS",
    "get_kr_valuation",
]
