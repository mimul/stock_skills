"""src/data/yahoo_client/us_session.py 테스트 — 미국 본장 판정과 나스닥 선물 세션 구분."""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.yahoo_client.us_session import (
    SESSION_NIGHT,
    SESSION_REGULAR,
    US_EASTERN,
    is_us_regular_session,
    nasdaq_session,
    session_window_start,
    to_eastern,
)

KST = ZoneInfo("Asia/Seoul")


def _et(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=US_EASTERN)


class TestIsUsRegularSession:
    """평일 09:30~16:00 ET 만 본장으로 본다 (16:00 은 포함하지 않음)."""

    @pytest.mark.parametrize(
        "now, expected",
        [
            (_et(2026, 10, 28, 12, 0), True),    # 수요일 정오
            (_et(2026, 10, 28, 9, 29), False),   # 개장 1분 전
            (_et(2026, 10, 28, 9, 30), True),    # 개장 시각(포함)
            (_et(2026, 10, 28, 15, 59), True),   # 마감 1분 전
            (_et(2026, 10, 28, 16, 0), False),   # 마감 시각(미포함)
            (_et(2026, 10, 28, 20, 0), False),   # 애프터마켓
            (_et(2026, 10, 31, 12, 0), False),   # 토요일
            (_et(2026, 11, 1, 12, 0), False),    # 일요일
        ],
    )
    def test_window(self, now, expected):
        assert is_us_regular_session(now) is expected

    def test_converts_kst_to_eastern(self):
        # 2026-10-29 23:30 KST = 10/29 10:30 EDT (서머타임은 11/1 종료) → 본장
        assert is_us_regular_session(datetime(2026, 10, 29, 23, 30, tzinfo=KST)) is True
        # 2026-10-30 06:00 KST = 10/29 17:00 EDT → 마감 후
        assert is_us_regular_session(datetime(2026, 10, 30, 6, 0, tzinfo=KST)) is False

    def test_after_dst_end_uses_standard_time(self):
        # 2026-11-03 00:00 KST = 11/2 10:00 EST (서머타임 종료 뒤) → 본장
        assert is_us_regular_session(datetime(2026, 11, 3, 0, 0, tzinfo=KST)) is True

    def test_dst_start_boundary(self):
        # 2026-03-08 02:00 EST 에 서머타임 시작. 3/9(월) 23:00 KST = 10:00 EDT 본장
        assert is_us_regular_session(datetime(2026, 3, 9, 23, 0, tzinfo=KST)) is True
        # 3/7(토) 00:00 KST = 3/6(금) 10:00 EST 본장
        assert is_us_regular_session(datetime(2026, 3, 7, 0, 0, tzinfo=KST)) is True
        # 3/9(월) 22:00 KST = 09:00 EDT → 개장 전
        assert is_us_regular_session(datetime(2026, 3, 9, 22, 0, tzinfo=KST)) is False

    def test_naive_datetime_is_treated_as_local_time(self):
        """naive 는 시스템 로컬 시각으로 본다 → tz 를 붙인 뒤 변환한 결과와 같아야 한다."""
        naive = datetime(2026, 10, 28, 23, 30)
        assert is_us_regular_session(naive) is is_us_regular_session(naive.astimezone())

    def test_default_now_uses_current_time(self, monkeypatch):
        import src.data.yahoo_client.us_session as mod

        monkeypatch.setattr(mod, "_now_eastern", lambda: _et(2026, 10, 28, 12, 0))
        assert is_us_regular_session() is True


class TestToEastern:
    def test_tz_aware_is_converted(self):
        out = to_eastern(datetime(2026, 10, 29, 23, 30, tzinfo=KST))
        assert out.tzinfo is US_EASTERN
        assert (out.hour, out.minute) == (10, 30)

    def test_naive_is_interpreted_as_local_and_shifted(self):
        naive = datetime(2026, 10, 28, 12, 0)
        out = to_eastern(naive)
        assert out.tzinfo is US_EASTERN
        assert out == naive.astimezone(US_EASTERN)


class TestNasdaqSession:
    def test_regular(self):
        assert nasdaq_session(_et(2026, 10, 28, 12, 0)) == SESSION_REGULAR == "regular"

    def test_night_after_close_and_premarket(self):
        assert nasdaq_session(_et(2026, 10, 28, 18, 30)) == SESSION_NIGHT == "night"
        assert nasdaq_session(_et(2026, 10, 29, 8, 0)) == SESSION_NIGHT

    def test_korean_trading_hours_are_night(self):
        # 한국 장중 10:00 KST = 전날 21:00 EDT
        assert nasdaq_session(datetime(2026, 10, 30, 10, 0, tzinfo=KST)) == SESSION_NIGHT

    def test_weekend_is_night(self):
        assert nasdaq_session(_et(2026, 10, 31, 12, 0)) == SESSION_NIGHT


class TestSessionWindowStart:
    def test_regular_starts_at_open_same_day(self):
        assert session_window_start(_et(2026, 10, 28, 12, 0)) == _et(2026, 10, 28, 9, 30)

    def test_night_after_18_starts_same_day_18(self):
        assert session_window_start(_et(2026, 10, 28, 21, 0)) == _et(2026, 10, 28, 18, 0)

    def test_night_before_18_starts_previous_day_18(self):
        assert session_window_start(_et(2026, 10, 29, 8, 0)) == _et(2026, 10, 28, 18, 0)
        # 마감 직후 16:00~18:00 구간도 전날 18:00 기준
        assert session_window_start(_et(2026, 10, 28, 16, 30)) == _et(2026, 10, 27, 18, 0)

    def test_kst_input_converted(self):
        # 10/30 10:00 KST = 10/29 21:00 EDT → 10/29 18:00 EDT
        out = session_window_start(datetime(2026, 10, 30, 10, 0, tzinfo=KST))
        assert out == _et(2026, 10, 29, 18, 0)

    def test_dst_end_night_window_keeps_wall_clock(self):
        # 서머타임 종료일(11/1 일) 새벽: 전날 10/31 18:00 EDT 가 창 시작 (벽시계 기준 18:00)
        out = session_window_start(_et(2026, 11, 1, 3, 0))
        assert (out.hour, out.minute, out.day) == (18, 0, 31)
