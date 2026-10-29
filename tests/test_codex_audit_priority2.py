"""Tests for KIK-743 Codex Audit Priority 2 fixes."""

import json
import time
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. yahoo_client/detail.py — try 블록 내 변수의 미정의 참조 회피
# ---------------------------------------------------------------------------


def test_yahoo_detail_init_outside_try_blocks():
    """KIK-743: try 바깥에서 dividend_paid_history 등이 초기화되는지 소스 확인.

    실 API 모킹은 복잡하므로 소스 정적 검사로 초기화 위치를 보장한다.
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src/data/yahoo_client/detail.py"
    text = src.read_text()
    # cashflow 블록 초기화가 try 보다 앞에 있어야 함
    cf_init = text.find("dividend_paid_history: list[float] = []")
    cf_try = text.find("cf = ticker.cashflow")
    assert 0 < cf_init < cf_try, "dividend_paid_history must be initialized BEFORE cashflow try"
    # ETF 계열: expense_ratio = None 초기화와 그 뒤의 대입
    etf_init = text.find('expense_ratio: Optional[float] = None')
    # 대입(타입 주석 없음)은 init 보다 뒤에 있음
    etf_assign = text.find('expense_ratio = _safe_get(info, "annualReportExpenseRatio")')
    assert 0 < etf_init < etf_assign, (
        "expense_ratio must be initialized to None BEFORE its try-block assignment"
    )


def test_yahoo_detail_no_remaining_try_only_init():
    """try 블록 안에서만 `expense_ratio: Optional` 타입 주석 재대입이 없어야 한다."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src/data/yahoo_client/detail.py"
    text = src.read_text()
    # `expense_ratio: Optional[float] = _safe_get` 패턴이 남아 있으면 NG
    # (try 바깥 초기화 + try 안 대입 패턴으로 바뀌었는지 확인)
    assert "expense_ratio: Optional[float] = _safe_get" not in text, (
        "expense_ratio should be re-assigned inside try without type annotation"
    )


# ---------------------------------------------------------------------------
# 2. save_report / save_screen / save_research / save_health 의 같은 날 덮어쓰기 방지
# ---------------------------------------------------------------------------


def test_save_report_unique_filename(tmp_path):
    from src.data.history.save_report import save_report

    p1 = save_report(
        "AAPL", {"x": 1}, score=0.5, verdict="hold",
        base_dir=str(tmp_path),
    )
    time.sleep(1.1)
    p2 = save_report(
        "AAPL", {"x": 2}, score=0.6, verdict="buy",
        base_dir=str(tmp_path),
    )
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


def test_save_screening_unique_filename(tmp_path):
    from src.data.history.save_screen import save_screening

    p1 = save_screening(
        "alpha", "us", [{"symbol": "AAPL"}], base_dir=str(tmp_path),
    )
    time.sleep(1.1)
    p2 = save_screening(
        "alpha", "us", [{"symbol": "MSFT"}], base_dir=str(tmp_path),
    )
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


def test_save_health_unique_filename(tmp_path):
    from src.data.history.save_health import save_health

    health_data = {"summary": {"total": 0, "healthy": 0}, "positions": []}
    p1 = save_health(health_data, base_dir=str(tmp_path))
    time.sleep(1.1)
    p2 = save_health(health_data, base_dir=str(tmp_path))
    assert p1 != p2
    assert Path(p1).exists() and Path(p2).exists()


# ---------------------------------------------------------------------------
# 3. watchlist 형식 불일치: list 형식과 dict 형식 모두 읽을 수 있음
# ---------------------------------------------------------------------------


def test_fallback_context_reads_list_format_watchlist(tmp_path, monkeypatch):
    """tools/watchlist.py 가 저장하는 list 형식 ["AAPL", "MSFT"] 을 읽을 수 있다."""
    from src.data.context import fallback_context as fc

    wl_dir = tmp_path / "watchlists"
    wl_dir.mkdir()
    (wl_dir / "default.json").write_text(json.dumps(["AAPL", "MSFT"]))

    monkeypatch.setattr(fc, "_WATCHLIST_DIR", str(wl_dir))
    assert fc._is_bookmarked_local("AAPL") is True
    assert fc._is_bookmarked_local("MSFT") is True
    assert fc._is_bookmarked_local("GOOGL") is False


def test_fallback_context_reads_legacy_dict_format(tmp_path, monkeypatch):
    """legacy {"symbols": [...]} 형식도 읽을 수 있다 (하위 호환)."""
    from src.data.context import fallback_context as fc

    wl_dir = tmp_path / "watchlists"
    wl_dir.mkdir()
    (wl_dir / "legacy.json").write_text(
        json.dumps({"symbols": ["AAPL", "MSFT"]})
    )

    monkeypatch.setattr(fc, "_WATCHLIST_DIR", str(wl_dir))
    assert fc._is_bookmarked_local("AAPL") is True
    assert fc._is_bookmarked_local("GOOGL") is False


# ---------------------------------------------------------------------------
# 4. graph_store mode cache reset
# ---------------------------------------------------------------------------


def test_reset_mode_cache_function_exists():
    from src.data.graph_store._common import reset_mode_cache, _mode_cache  # noqa: F401
    # 호출 가능한지 확인
    reset_mode_cache()


def test_mode_cache_reset_clears_cached_value(monkeypatch):
    from src.data.graph_store import _common as gc

    # 일단 full 로 설정
    gc._mode_cache = ("full", time.time())
    assert gc._mode_cache[0] == "full"

    gc.reset_mode_cache()
    assert gc._mode_cache == ("", 0.0)
