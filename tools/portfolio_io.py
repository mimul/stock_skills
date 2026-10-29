"""Portfolio I/O Tool — PF CSV 읽기/쓰기 파사드.

tools/ 층은 저장·조회만 담당한다. 판단 로직은 포함하지 않는다.
src/data/portfolio_io 의 순수 데이터 조작 함수를 re-export 한다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.portfolio_io import (  # noqa: E402
    load_portfolio,
    save_portfolio,
    add_position,
    sell_position,
    update_next_earnings,
    get_performance_review,
    DEFAULT_CSV_PATH,
    # KIK-734: PF 총자산(주식+현금)의 SSoT
    load_cash_balance,
    load_total_assets,
    DEFAULT_CASH_PATH,
)

__all__ = [
    "load_portfolio",
    "save_portfolio",
    "add_position",
    "sell_position",
    "update_next_earnings",
    "get_performance_review",
    "DEFAULT_CSV_PATH",
    # KIK-734
    "load_cash_balance",
    "load_total_assets",
    "DEFAULT_CASH_PATH",
]
