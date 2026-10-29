"""Scoring Tool — 3축 품질 스코어링 파사드 (KIK-708).

tools/ 층은 외부 API 접속만 담당한다. 판단 로직(스코어 계산 등)은 포함하지 않는다.
src/data/scoring.py 의 함수를 re-export 한다.
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.scoring import (  # noqa: E402
    score_return,
    score_growth,
    score_durability,
    score_quality,
    score_portfolio,
)

__all__ = [
    "score_return",
    "score_growth",
    "score_durability",
    "score_quality",
    "score_portfolio",
]
