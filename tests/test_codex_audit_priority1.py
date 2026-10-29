"""Tests for KIK-742 Codex Audit Priority 1 fixes."""

import json
import time
from datetime import date, datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. save_trade.py — 파일명 유일화
# ---------------------------------------------------------------------------


def test_save_trade_filename_unique_for_same_day_same_symbol(tmp_path, monkeypatch):
    """같은 날·같은 종목·같은 타입으로 2회 호출해도 파일이 충돌하지 않는다."""
    from src.data.history.save_trade import save_trade

    base = tmp_path
    today = date.today().isoformat()
    p1 = save_trade(
        symbol="AAPL",
        trade_type="buy",
        shares=10,
        price=150.0,
        currency="USD",
        date_str=today,
        memo="first",
        base_dir=str(base / "history"),
    )
    # 시각을 살짝 어긋나게 함 (같은 초 회피)
    time.sleep(1.1)
    p2 = save_trade(
        symbol="AAPL",
        trade_type="buy",
        shares=5,
        price=151.0,
        currency="USD",
        date_str=today,
        memo="second",
        base_dir=str(base / "history"),
    )

    assert p1 != p2, "filenames must be unique"
    assert Path(p1).exists()
    assert Path(p2).exists()
    # 두 파일 모두 남아 있음 (덮어쓰이지 않음)
    rec1 = json.loads(Path(p1).read_text())
    rec2 = json.loads(Path(p2).read_text())
    assert rec1["memo"] == "first"
    assert rec2["memo"] == "second"


# ---------------------------------------------------------------------------
# 2. session_state.py — date 키 폴백
# ---------------------------------------------------------------------------


def test_session_state_recognizes_date_key_from_save_trade(tmp_path):
    """save_trade 가 `date` 키로 저장한 파일을 recent_trades 가 집어 올린다."""
    from src.data import session_state

    trade_dir = tmp_path / "data" / "history" / "trade"
    trade_dir.mkdir(parents=True)
    today = date.today().isoformat()
    rec = {
        "category": "trade",
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "symbol": "AAPL",
        "trade_type": "buy",
        "shares": 10,
        "price": 150.0,
        "currency": "USD",
        "memo": "test",
    }
    f = trade_dir / f"{today}_buy_AAPL_120000.json"
    f.write_text(json.dumps(rec))

    result = session_state.reconcile_session_state(
        base_dir=str(tmp_path), trade_window_days=7
    )
    assert f.name in result["recent_trades"]


def test_session_state_legacy_trade_date_still_works(tmp_path):
    """legacy `trade_date` 키도 인식된다 (하위 호환)."""
    from src.data import session_state

    trade_dir = tmp_path / "data" / "history" / "trade"
    trade_dir.mkdir(parents=True)
    today = date.today().isoformat()
    rec = {
        "category": "trade",
        "trade_date": today,  # legacy
        "symbol": "AAPL",
    }
    f = trade_dir / "legacy_trade.json"
    f.write_text(json.dumps(rec))

    result = session_state.reconcile_session_state(
        base_dir=str(tmp_path), trade_window_days=7
    )
    assert f.name in result["recent_trades"]


# ---------------------------------------------------------------------------
# 3. cash_balance.py — 계층 형식 SSoT
# ---------------------------------------------------------------------------


def test_cash_balance_hierarchical_save_load_roundtrip(tmp_path):
    """계층 형식으로 저장→로드해도 데이터가 유지된다."""
    from tools import cash_balance

    path = str(tmp_path / "cash.json")
    payload = {
        "date": "2026-04-29",
        "total_krw": 10_000_000,
        "breakdown": {
            "USD": {
                "amount": 2000.0,
                "krw_equivalent": 2_800_000,
                "rate_krw_per_usd": 1400.0,
            },
            "KRW": {"amount": 7_200_000},
        },
    }
    cash_balance.save_cash_balance(payload.copy(), path)
    loaded = cash_balance.load_cash_balance(path)
    assert loaded["total_krw"] == 10_000_000
    assert loaded["breakdown"]["USD"]["amount"] == 2000.0
    assert "timestamp" in loaded  # save 시 자동 부여


def test_cash_balance_update_currency_hierarchical(tmp_path):
    """update_currency 가 계층 형식 breakdown 에 기록된다."""
    from tools import cash_balance

    path = str(tmp_path / "cash.json")
    cash_balance.update_currency(
        "USD", 1000.0, path=path,
        krw_equivalent=1_400_000, rate_krw_per_usd=1400.0,
    )
    data = cash_balance.load_cash_balance(path)
    assert "breakdown" in data
    assert data["breakdown"]["USD"]["amount"] == 1000.0
    assert data["breakdown"]["USD"]["krw_equivalent"] == 1_400_000
    assert data["breakdown"]["USD"]["rate_krw_per_usd"] == 1400.0


# ---------------------------------------------------------------------------
# 4. portfolio_io.py — 입력 검증
# ---------------------------------------------------------------------------


def _empty_portfolio_csv(tmp_path):
    p = tmp_path / "portfolio.csv"
    p.write_text(
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    return str(p)


def test_add_position_rejects_zero_shares(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="shares"):
        add_position(csv_path, "AAPL", shares=0, cost_price=100)


def test_add_position_rejects_negative_shares(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="shares"):
        add_position(csv_path, "AAPL", shares=-5, cost_price=100)


def test_add_position_rejects_zero_cost_price(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="cost_price"):
        add_position(csv_path, "AAPL", shares=10, cost_price=0)


def test_add_position_rejects_negative_cost_price(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    with pytest.raises(ValueError, match="cost_price"):
        add_position(csv_path, "AAPL", shares=10, cost_price=-10)


def test_sell_position_rejects_zero_shares(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="shares"):
        sell_position(csv_path, "AAPL", shares=0)


def test_sell_position_rejects_negative_shares(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="shares"):
        sell_position(csv_path, "AAPL", shares=-3)


def test_sell_position_rejects_negative_sell_price(tmp_path):
    from src.data.portfolio_io import add_position, sell_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=100)
    with pytest.raises(ValueError, match="sell_price"):
        sell_position(csv_path, "AAPL", shares=5, sell_price=-50)


def test_add_position_normal_path_still_works(tmp_path):
    """정상 케이스 (기존 테스트 상당)."""
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    result = add_position(csv_path, "AAPL", shares=10, cost_price=150.5)
    assert result["shares"] == 10
    assert result["cost_price"] == 150.5
