"""portfolio_io.load_total_assets / load_cash_balance 테스트 (KIK-734)."""

from __future__ import annotations

import json

import pytest

from src.data.portfolio_io import (
    load_cash_balance,
    load_total_assets,
)


def _write_csv(path, rows: list[dict]) -> None:
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    body = "\n".join(
        f"{r['symbol']},{r['shares']},{r['cost_price']},{r.get('cost_currency','KRW')},"
        f",{r.get('memo','')},{r.get('next_earnings','')},,,,,{r.get('role','')}"
        for r in rows
    )
    path.write_text(header + body + "\n", encoding="utf-8")


def _write_cash(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestLoadCashBalance:
    def test_returns_empty_when_missing(self, tmp_path):
        result = load_cash_balance(str(tmp_path / "missing.json"))
        assert result == {}

    def test_returns_dict_when_exists(self, tmp_path):
        cash_path = tmp_path / "cash.json"
        _write_cash(cash_path, {
            "total_krw": 8_709_690,
            "breakdown": {"USD": {"amount": 4435.32}, "KRW": {"amount": 2339690}},
        })
        result = load_cash_balance(str(cash_path))
        assert result["total_krw"] == 8_709_690
        assert result["breakdown"]["USD"]["amount"] == 4435.32


class TestLoadTotalAssets:
    def test_returns_both_positions_and_cash(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [
            {"symbol": "035420.KS", "shares": 8, "cost_price": 210000, "role": "장기인컴"},
            {"symbol": "AAPL", "shares": 5, "cost_price": 200.0, "cost_currency": "USD", "role": "성장"},
        ])
        _write_cash(cash_path, {"total_krw": 8_709_690, "breakdown": {}})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert len(result["positions"]) == 2
        assert result["cash"]["total_krw"] == 8_709_690
        assert result["cash_krw"] == 8_709_690
        assert result["has_cash"] is True

    def test_default_cost_currency_is_krw(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        csv_path.write_text(
            "symbol,shares,cost_price,cost_currency\n005930.KS,10,72000,\n",
            encoding="utf-8",
        )
        result = load_total_assets(str(csv_path), str(tmp_path / "missing.json"))
        assert result["positions"][0]["cost_currency"] == "KRW"

    def test_has_cash_false_when_missing(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        _write_csv(csv_path, [
            {"symbol": "AAPL", "shares": 1, "cost_price": 200.0, "cost_currency": "USD"},
        ])
        result = load_total_assets(str(csv_path), str(tmp_path / "missing.json"))
        assert result["has_cash"] is False
        assert result["cash_krw"] == 0.0

    def test_empty_portfolio(self, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [])
        _write_cash(cash_path, {"total_krw": 10_000_000})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert result["positions"] == []
        assert result["cash_krw"] == 10_000_000

    def test_cash_total_krw_missing_marks_has_cash_false(self, tmp_path):
        """KIK-734 리뷰: cash_balance.json 이 손상되어 total_krw 가 빠진 경우
        has_cash=False 로 취급한다 (cash_krw=0 과 정합성 유지)."""
        csv_path = tmp_path / "portfolio.csv"
        cash_path = tmp_path / "cash.json"
        _write_csv(csv_path, [])
        _write_cash(cash_path, {"breakdown": {"USD": {"amount": 100}}})

        result = load_total_assets(str(csv_path), str(cash_path))
        assert result["cash_krw"] == 0.0
        assert result["has_cash"] is False  # total_krw 누락 → False
        assert "breakdown" in result["cash"]  # 원본 cash dict 는 유지
