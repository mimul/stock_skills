"""Preflight Tool — DeepThink 기동 전 게이트 파사드 (KIK-735).

tools/ 층은 API 호출만 담당한다. 판단 로직은 포함하지 않는다.
src/data/preflight 의 순수 함수를 re-export 한다.
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.preflight import (  # noqa: E402
    PreflightError,
    run_preflight,
    extract_convictions,
)

__all__ = [
    "PreflightError",
    "run_preflight",
    "extract_convictions",
]
