"""미국 본장(정규장) 판정과 나스닥 선물 세션 구분.

나스닥의 대리 지표로는 거의 24시간 거래되는 나스닥100 선물(NQ=F)을 항상 쓴다.
다만 어느 세션의 움직임인지 구분한다:

- ``regular``: 미국 본장(평일 09:30 ≤ t < 16:00 America/New_York). 본장 세션의 선물 변동
  (09:30 ET 이후)을 본다.
- ``night``: 그 외 시간(마감 후·프리마켓·주말). 야간 세션의 선물 변동(직전 18:00 ET
  이후)을 본다. 한국 장중은 전부 이 구간이며, 야간 선물 변동은 한국 장의 선행 신호다.

알려진 한계:
- 미국 휴장일·CME 휴장일은 달력으로 판정하지 않는다. 세션 창에 봉이 없으면
  ``session_change`` 가 None 이 된다.
- 조기 마감일(13:00 ET 마감)은 13:00~16:00 에도 regular 로 판정한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

US_EASTERN = ZoneInfo("America/New_York")

REGULAR_OPEN = dtime(9, 30)
REGULAR_CLOSE = dtime(16, 0)  # 마감 시각은 포함하지 않는다
NIGHT_OPEN = dtime(18, 0)  # CME 글로벡스 야간 세션 시작

NASDAQ_FUTURES = "NQ=F"

SESSION_REGULAR = "regular"
SESSION_NIGHT = "night"


def _now_eastern() -> datetime:
    """현재 시각(ET). 테스트에서 고정하기 위해 분리."""
    return datetime.now(US_EASTERN)


def to_eastern(now: datetime | None = None) -> datetime:
    """시각을 미국 동부시간으로 맞춘다.

    - None → 현재 시각(ET)
    - tz-aware → ET 로 변환
    - naive → **시스템 로컬 시각**으로 보고 ET 로 변환한다. 한국 머신에서
      ``datetime.now()`` 를 그대로 넘겨도 KST 로 해석되어 어긋나지 않는다.
    """
    if now is None:
        return _now_eastern()
    return now.astimezone(US_EASTERN)


def is_us_regular_session(now: datetime | None = None) -> bool:
    """주어진 시각이 미국 정규장(평일 09:30 ≤ t < 16:00 ET) 안인지 판정한다."""
    et = to_eastern(now)
    if et.weekday() >= 5:  # 토(5)·일(6)
        return False
    return REGULAR_OPEN <= et.time() < REGULAR_CLOSE


def nasdaq_session(now: datetime | None = None) -> str:
    """본장이면 ``regular``, 아니면 ``night``."""
    return SESSION_REGULAR if is_us_regular_session(now) else SESSION_NIGHT


def session_window_start(now: datetime | None = None) -> datetime:
    """현재 세션의 시작 시각(ET).

    - regular: 당일 09:30 ET
    - night: 직전 18:00 ET (18:00 이전이면 전날 18:00). 주말에는 금요일 18:00 이 되어
      봉이 없을 수 있다 (CME 는 일요일 18:00 재개).
    """
    et = to_eastern(now)
    if is_us_regular_session(et):
        return et.replace(hour=9, minute=30, second=0, microsecond=0)
    start = et.replace(hour=18, minute=0, second=0, microsecond=0)
    if et.time() < NIGHT_OPEN:
        start -= timedelta(days=1)
    return start
