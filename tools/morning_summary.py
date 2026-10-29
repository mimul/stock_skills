"""Morning Summary Tool — 아침 요약 파사드 (KIK-717).

tools/ 층은 외부 API 접속만 담당한다. 판단 로직은 포함하지 않는다.
src/data/morning_summary.py 의 함수를 re-export 한다.
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.morning_summary import (  # noqa: E402
    detect_alerts,
    format_morning_summary,
    ALERT_THRESHOLDS,
)

__all__ = [
    "detect_alerts",
    "format_morning_summary",
    "ALERT_THRESHOLDS",
]
