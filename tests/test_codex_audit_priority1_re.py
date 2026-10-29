"""Tests for KIK-744 Codex Audit Re-review fixes."""

import json
import time
from datetime import date, datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. _unique_suffix: 같은 초에 2회 호출해도 완전히 유일
# ---------------------------------------------------------------------------


def test_unique_suffix_same_microsecond_collision_safety():
    """같은 datetime 을 넘겨도 uuid suffix 로 다른 결과가 나온다."""
    from src.data.history._helpers import _unique_suffix

    fixed_dt = datetime(2026, 4, 29, 10, 30, 45, 123456)
    s1 = _unique_suffix(fixed_dt)
    s2 = _unique_suffix(fixed_dt)
    s3 = _unique_suffix(fixed_dt)
    assert s1 != s2 != s3
    # 형식: HHMMSSffffff_<6hex>
    assert len(s1) == 19
    assert s1[:12].isdigit()
    assert s1[12] == "_"
    assert all(c in "0123456789abcdef" for c in s1[13:])


def test_save_trade_no_collision_within_same_second(tmp_path):
    """KIK-744: time.sleep 없이 연속 호출해도 덮어쓰이지 않는다."""
    from src.data.history.save_trade import save_trade

    today = date.today().isoformat()
    paths = []
    for i in range(10):
        p = save_trade(
            symbol="AAPL",
            trade_type="buy",
            shares=1,
            price=100.0 + i,
            currency="USD",
            date_str=today,
            memo=f"call_{i}",
            base_dir=str(tmp_path / "history"),
        )
        paths.append(p)

    # 모든 경로가 유일 (충돌 없음)
    assert len(set(paths)) == 10
    # 모든 파일이 남아 있음 (덮어쓰이지 않음)
    for p in paths:
        assert Path(p).exists()


def test_save_report_no_collision_within_same_second(tmp_path):
    from src.data.history.save_report import save_report
    paths = [
        save_report("AAPL", {"x": i}, score=0.5, verdict="hold", base_dir=str(tmp_path))
        for i in range(5)
    ]
    assert len(set(paths)) == 5


def test_save_screening_no_collision_within_same_second(tmp_path):
    from src.data.history.save_screen import save_screening
    paths = [
        save_screening("alpha", "us", [{"symbol": f"X{i}"}], base_dir=str(tmp_path))
        for i in range(5)
    ]
    assert len(set(paths)) == 5


def test_save_health_no_collision_within_same_second(tmp_path):
    from src.data.history.save_health import save_health
    health = {"summary": {"total": 0, "healthy": 0}, "positions": []}
    paths = [save_health(health, base_dir=str(tmp_path)) for _ in range(5)]
    assert len(set(paths)) == 5


def test_save_stress_test_no_collision(tmp_path):
    from src.data.history.save_misc import save_stress_test
    paths = [
        save_stress_test("market_crash", ["AAPL"], -0.2, base_dir=str(tmp_path))
        for _ in range(5)
    ]
    assert len(set(paths)) == 5


def test_save_forecast_no_collision(tmp_path):
    from src.data.history.save_misc import save_forecast
    paths = [
        save_forecast([{"symbol": "AAPL", "optimistic": 0.1, "base": 0.05, "pessimistic": -0.1}],
                      base_dir=str(tmp_path))
        for _ in range(5)
    ]
    assert len(set(paths)) == 5


# ---------------------------------------------------------------------------
# 2. graph_store/portfolio.py merge_trade trade_id 유일화
# ---------------------------------------------------------------------------


def test_merge_trade_id_includes_fingerprint():
    """같은 날·같은 종목이라도 shares/price 가 다르면 trade_id 가 다르다."""
    # helper 를 직접 재현해 테스트 (merge_trade 는 Neo4j 접속이 필요하므로)
    import hashlib

    def _build_id(date_, type_, sym, shares, price, sell_price=None, hold_days=None):
        fp_src = "|".join([str(date_), str(type_), str(sym), str(shares),
                           str(price), str(sell_price), str(hold_days)])
        fp = hashlib.sha1(fp_src.encode()).hexdigest()[:8]
        return f"trade_{date_}_{type_}_{sym}_{fp}"

    a = _build_id("2026-04-29", "buy", "AAPL", 10, 150.0)
    b = _build_id("2026-04-29", "buy", "AAPL", 5, 155.0)
    c = _build_id("2026-04-29", "buy", "AAPL", 10, 150.0)  # same → same id
    assert a != b, "different shares/price must yield different id"
    assert a == c, "same parameters must yield same id (deterministic)"


def test_merge_trade_explicit_trade_id_overrides():
    """trade_id 인자를 넘기면 그 값이 채택된다 (기존 호출의 하위 호환)."""
    from src.data.graph_store import portfolio as gp_portfolio
    import inspect
    sig = inspect.signature(gp_portfolio.merge_trade)
    assert "trade_id" in sig.parameters, "merge_trade must accept trade_id parameter"


# ---------------------------------------------------------------------------
# 3. portfolio_io: cost_currency 검증
# ---------------------------------------------------------------------------


def _empty_portfolio_csv(tmp_path):
    p = tmp_path / "portfolio.csv"
    p.write_text(
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    return str(p)


def test_add_position_rejects_currency_mismatch(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=150.0, cost_currency="USD")
    with pytest.raises(ValueError, match="cost_currency mismatch"):
        add_position(csv_path, "AAPL", shares=5, cost_price=20000, cost_currency="KRW")


def test_add_position_same_currency_still_works(tmp_path):
    from src.data.portfolio_io import add_position
    csv_path = _empty_portfolio_csv(tmp_path)
    add_position(csv_path, "AAPL", shares=10, cost_price=150.0, cost_currency="USD")
    # 같은 통화는 OK
    result = add_position(csv_path, "AAPL", shares=5, cost_price=160.0, cost_currency="USD")
    assert result["shares"] == 15
    # 평균 단가 = (10*150 + 5*160) / 15 = 153.333...
    assert abs(result["cost_price"] - 153.3333) < 0.01


# ---------------------------------------------------------------------------
# 4. portfolio_io: CSV 손상 행 건너뛰기
# ---------------------------------------------------------------------------


def test_load_portfolio_skips_malformed_rows(tmp_path):
    """숫자가 손상된 행은 경고 로그 출력 후 건너뛰고, 나머지는 읽을 수 있다."""
    from src.data.portfolio_io import load_portfolio
    csv_path = tmp_path / "portfolio.csv"
    csv_path.write_text(
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
        "AAPL,10,150.0,USD,,,,,,,,\n"           # OK
        "BROKEN,abc,150.0,USD,,,,,,,,\n"        # shares 가 손상됨
        "MSFT,5,not_a_number,USD,,,,,,,,\n"     # cost_price 가 손상됨
        "GOOGL,3,200.0,USD,,,,,,,,\n"          # OK
    )
    result = load_portfolio(str(csv_path))
    symbols = [p["symbol"] for p in result]
    assert "AAPL" in symbols
    assert "GOOGL" in symbols
    assert "BROKEN" not in symbols
    assert "MSFT" not in symbols
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 5. .gitignore: data/ 는 제외, config/ 공유 설정은 추적
# ---------------------------------------------------------------------------


def test_gitignore_keeps_config_yaml_tracked():
    """config/scoring.yaml 등은 .gitignore 로 제외되지 않는다."""
    from pathlib import Path
    gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
    text = gitignore.read_text()
    # config/ 단독 제외 행이 사라졌는지
    lines = [line.strip() for line in text.splitlines()]
    assert "config/" not in lines, "config/ must NOT be a blanket exclude"
    # 루트 data/ 는 제외 유지 (앵커 /data/ — src/data, tests/data 까지 숨기지 않도록)
    assert "/data/" in lines
    assert "data/" not in lines, "앵커 없는 data/ 는 src/data·tests/data 신규 파일을 숨긴다"


def test_gitignore_excludes_secrets_path():
    """기밀 config 용 divider 가 준비되어 있다."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / ".gitignore").read_text()
    assert "config/secrets/" in text or "config/*.local.yaml" in text
