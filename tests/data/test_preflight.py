"""src.data.preflight 테스트 (KIK-735)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.preflight import (
    PreflightError,
    extract_convictions,
    run_preflight,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    body = "\n".join(
        f"{r['symbol']},{r['shares']},{r['cost_price']},{r.get('cost_currency','KRW')},"
        f",{r.get('memo','')},,,,,,"
        for r in rows
    )
    path.write_text(header + body + "\n", encoding="utf-8")


def _write_cash(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_thesis(notes_dir: Path, symbol: str, content: str,
                  source: str = "manual", date: str = "2026-04-25") -> None:
    fp = notes_dir / f"{date}_{symbol.replace('.', '_')}_thesis.json"
    fp.write_text(
        json.dumps([{
            "id": f"note_{date}_{symbol}",
            "date": date,
            "symbol": symbol,
            "type": "thesis",
            "content": content,
            "source": source,
        }], ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    notes_dir = data_dir / "notes"
    notes_dir.mkdir(parents=True)
    csv_path = data_dir / "portfolio.csv"
    cash_path = data_dir / "cash_balance.json"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CSV_PATH", str(csv_path),
    )
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CASH_PATH", str(cash_path),
    )

    return {
        "notes_dir": notes_dir,
        "csv_path": csv_path,
        "cash_path": cash_path,
    }


# ---------------------------------------------------------------------------
# extract_convictions
# ---------------------------------------------------------------------------


class TestExtractConvictions:
    def test_detects_hold_confirmed_keyword(self, env):
        _write_thesis(env["notes_dir"], "035420.KS", "【홀드확정 4/25】팔지 않음")
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["035420.KS"]

    def test_detects_user_conviction_source(self, env):
        _write_thesis(
            env["notes_dir"], "AMZN", "강세 유지",
            source="user-conviction+3llm",
        )
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["AMZN"]

    def test_no_conviction_returns_empty(self, env):
        _write_thesis(env["notes_dir"], "AAPL", "일반적인 thesis")
        assert extract_convictions(notes_dir=str(env["notes_dir"])) == []

    def test_dedupe_multiple_thesis_same_symbol(self, env):
        _write_thesis(
            env["notes_dir"], "035420.KS", "홀드 확정 1", date="2026-04-20",
        )
        _write_thesis(
            env["notes_dir"], "035420.KS", "홀드 확정 2", date="2026-04-25",
        )
        convs = extract_convictions(notes_dir=str(env["notes_dir"]))
        assert convs == ["035420.KS"]


# ---------------------------------------------------------------------------
# run_preflight (PF 도메인)
# ---------------------------------------------------------------------------


class TestRunPreflightPf:
    def test_valid_pf_passes(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "035420.KS", "shares": 8, "cost_price": 210000},
        ])
        _write_cash(env["cash_path"], {"total_krw": 8_709_690})
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is True
        assert result["violations"] == []
        assert result["context"]["cash_krw"] == 8_709_690
        assert result["context"]["positions_count"] == 1

    def test_missing_cash_total_krw_fails(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200, "cost_currency": "USD"},
        ])
        _write_cash(env["cash_path"], {"breakdown": {}})
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False
        assert any("total_krw" in v for v in result["violations"])

    def test_no_cash_file_fails(self, env):
        _write_csv(env["csv_path"], [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200, "cost_currency": "USD"},
        ])
        # cash_path 가 존재하지 않음
        result = run_preflight(domain="pf", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# run_preflight (proposed_actions)
# ---------------------------------------------------------------------------


class TestRunPreflightProposedActions:
    def test_invalid_shares_blocks(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_krw": 10_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=[("sell", "005930.KS", 0)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False
        assert any("양의 정수" in v for v in result["violations"])

    def test_conviction_violation_blocks(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_krw": 10_000_000})
        _write_thesis(env["notes_dir"], "035420.KS", "【홀드확정】팔지 않음")
        result = run_preflight(
            domain="pf",
            proposed_actions=[("trim", "035420.KS", 3)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False
        assert any("conviction" in v for v in result["violations"])

    def test_valid_actions_pass(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_krw": 10_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=[("sell", "AMZN", 5), ("buy", "005930.KS", 3)],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is True

    def test_invalid_action_format(self, env):
        _write_csv(env["csv_path"], [])
        _write_cash(env["cash_path"], {"total_krw": 10_000_000})
        result = run_preflight(
            domain="pf",
            proposed_actions=["not-a-tuple"],
            notes_dir=str(env["notes_dir"]),
        )
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# run_preflight (market/sector/stock 도메인)
# ---------------------------------------------------------------------------


class TestRunPreflightOtherDomains:
    def test_market_domain_emits_warning_only(self, env):
        result = run_preflight(domain="market", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is True
        assert len(result["warnings"]) >= 1

    def test_unknown_domain_fails(self, env):
        result = run_preflight(domain="zzz", notes_dir=str(env["notes_dir"]))
        assert result["passed"] is False
        assert any("unknown domain" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# PreflightError
# ---------------------------------------------------------------------------


class TestPreflightError:
    def test_raises_with_violations(self):
        with pytest.raises(PreflightError) as exc_info:
            raise PreflightError(["v1", "v2"])
        assert exc_info.value.violations == ["v1", "v2"]
        assert "v1" in str(exc_info.value)
