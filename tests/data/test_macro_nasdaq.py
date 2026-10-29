"""get_macro_indicators 의 나스닥 선물 세션 구분 로직 테스트 (실제 API 호출 없음)."""

import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yfinance as yf

from src.data.yahoo_client.macro import MACRO_TICKERS, NASDAQ_NAME, get_macro_indicators
from src.data.yahoo_client.us_session import NASDAQ_FUTURES, US_EASTERN

REGULAR = datetime(2026, 10, 28, 12, 0, tzinfo=US_EASTERN)  # 수요일 정오 ET
NIGHT = datetime(2026, 10, 28, 21, 0, tzinfo=US_EASTERN)    # 수요일 21:00 ET (한국 10/29 10:00)


def _daily(closes):
    return pd.DataFrame({"Close": closes})


def _intraday(rows, tz="America/New_York"):
    """[(ET 시각 문자열, open, close), ...] → 5분봉 DataFrame."""
    idx = pd.DatetimeIndex([r[0] for r in rows], tz=tz)
    return pd.DataFrame({"Open": [r[1] for r in rows], "Close": [r[2] for r in rows]}, index=idx)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)


def _install(monkeypatch, *, daily=None, intraday=None, intraday_error=None, calls=None):
    """NQ=F 는 interval 유무로 일봉/분봉을 구분해 돌려주고, 나머지 심볼은 일봉 더미."""

    def factory(symbol):
        if calls is not None:
            calls.append(symbol)
        t = MagicMock()

        def history(period="5d", interval=None):
            if symbol != NASDAQ_FUTURES:
                return _daily([100.0, 101.0])
            if interval is None:
                return daily if daily is not None else _daily([20000.0, 20200.0])
            if intraday_error is not None:
                raise intraday_error
            return intraday if intraday is not None else pd.DataFrame()

        t.history.side_effect = history
        return t

    monkeypatch.setattr(yf, "Ticker", factory)


def _nasdaq(result):
    return next(i for i in result if i["name"] == NASDAQ_NAME)


class TestMacroTickers:
    def test_nasdaq_is_futures_after_sp500(self):
        names = list(MACRO_TICKERS)
        assert names.index(NASDAQ_NAME) == names.index("S&P500") + 1
        assert MACRO_TICKERS[NASDAQ_NAME] == NASDAQ_FUTURES == "NQ=F"


class TestGetMacroIndicatorsNasdaq:
    def test_night_session_change_from_18_et(self, monkeypatch):
        """한국 장중(미국 야간): 18:00 ET 세션 시작 봉의 시가 대비 마지막 종가."""
        _install(
            monkeypatch,
            intraday=_intraday([
                ("2026-10-28 15:55", 20100.0, 20150.0),  # 본장 마지막 봉 (창 밖)
                ("2026-10-28 18:00", 20200.0, 20180.0),  # 야간 세션 첫 봉
                ("2026-10-28 20:55", 20100.0, 19998.0),
            ]),
        )
        entry = _nasdaq(get_macro_indicators(now=NIGHT))

        assert entry["symbol"] == NASDAQ_FUTURES
        assert entry["basis"] == "futures"
        assert entry["session"] == "night"
        assert entry["session_start"] == "2026-10-28T18:00:00-04:00"
        assert entry["session_change"] == pytest.approx((19998.0 - 20200.0) / 20200.0)
        assert entry["price"] == 20200.0            # 일봉 기준 현재값
        assert entry["daily_change"] == pytest.approx(0.01)  # 직전 정산 대비

    def test_regular_session_change_from_0930_et(self, monkeypatch):
        _install(
            monkeypatch,
            intraday=_intraday([
                ("2026-10-28 09:25", 20000.0, 20010.0),  # 프리마켓 (창 밖)
                ("2026-10-28 09:30", 20050.0, 20040.0),
                ("2026-10-28 11:55", 20300.0, 20351.0),
            ]),
        )
        entry = _nasdaq(get_macro_indicators(now=REGULAR))

        assert entry["session"] == "regular"
        assert entry["session_start"] == "2026-10-28T09:30:00-04:00"
        assert entry["session_change"] == pytest.approx((20351.0 - 20050.0) / 20050.0)

    def test_intraday_index_in_utc_is_converted(self, monkeypatch):
        # 2026-10-28 22:00 UTC = 18:00 EDT → 창 안
        _install(
            monkeypatch,
            intraday=_intraday([("2026-10-28 21:55", 1.0, 1.0), ("2026-10-28 22:00", 100.0, 110.0)], tz="UTC"),
        )
        entry = _nasdaq(get_macro_indicators(now=NIGHT))
        assert entry["session_change"] == pytest.approx(0.10)

    def test_no_bars_in_window_gives_none(self, monkeypatch):
        """주말·휴장: 세션 창에 봉이 없으면 session_change 만 None, 항목은 유지."""
        _install(monkeypatch, intraday=_intraday([("2026-10-27 18:00", 1.0, 1.0)]))
        entry = _nasdaq(get_macro_indicators(now=NIGHT))
        assert entry["session_change"] is None
        assert entry["price"] == 20200.0

    def test_intraday_exception_keeps_entry(self, monkeypatch):
        _install(monkeypatch, intraday_error=RuntimeError("boom"))
        result = get_macro_indicators(now=NIGHT)
        assert len(result) == len(MACRO_TICKERS)
        entry = _nasdaq(result)
        assert entry["session_change"] is None
        assert entry["price"] == 20200.0

    def test_empty_daily_still_reports_session(self, monkeypatch):
        _install(monkeypatch, daily=pd.DataFrame(), intraday=_intraday([("2026-10-28 18:00", 10.0, 11.0)]))
        entry = _nasdaq(get_macro_indicators(now=NIGHT))
        assert entry["price"] is None
        assert entry["session"] == "night"
        assert entry["session_change"] == pytest.approx(0.10)

    def test_daily_exception_skips_nasdaq_only(self, monkeypatch):
        def factory(symbol):
            t = MagicMock()
            if symbol == NASDAQ_FUTURES:
                t.history.side_effect = RuntimeError("down")
            else:
                t.history.return_value = _daily([100.0, 101.0])
            return t

        monkeypatch.setattr(yf, "Ticker", factory)
        result = get_macro_indicators(now=NIGHT)
        assert len(result) == len(MACRO_TICKERS) - 1
        assert all(i["name"] != NASDAQ_NAME for i in result)

    def test_default_now_uses_frozen_clock(self, monkeypatch):
        import src.data.yahoo_client.us_session as s

        _install(monkeypatch)
        monkeypatch.setattr(s, "_now_eastern", lambda: NIGHT)
        assert _nasdaq(get_macro_indicators())["session"] == "night"
        monkeypatch.setattr(s, "_now_eastern", lambda: REGULAR)
        assert _nasdaq(get_macro_indicators())["session"] == "regular"

    def test_non_nasdaq_entries_have_no_session_keys(self, monkeypatch):
        _install(monkeypatch)
        kospi = next(i for i in get_macro_indicators(now=NIGHT) if i["name"] == "KOSPI")
        assert "session" not in kospi and "session_change" not in kospi
