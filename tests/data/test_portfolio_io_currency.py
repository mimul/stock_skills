"""portfolio_io 통화 추론 테스트 (코드 리뷰 H3).

cost_currency 를 생략하면 심볼 접미사로 추론해야 한다.
미국 종목을 KRW 로 기록하면 손익이 환율 배수만큼 틀어진다.
"""

import pytest

from src.data.portfolio_io import add_position, load_portfolio

_HEADER = (
    "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
    "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
)


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "portfolio.csv"
    path.write_text(_HEADER, encoding="utf-8")
    return str(path)


class TestAddPositionCurrencyInference:
    def test_us_stock_defaults_to_usd(self, csv_path):
        result = add_position(csv_path, "AAPL", 3, 180.5)
        assert result["cost_currency"] == "USD"
        assert load_portfolio(csv_path)[0]["cost_currency"] == "USD"

    def test_korean_stock_defaults_to_krw(self, csv_path):
        result = add_position(csv_path, "005930.KS", 10, 72000)
        assert result["cost_currency"] == "KRW"

    def test_kosdaq_defaults_to_krw(self, csv_path):
        assert add_position(csv_path, "247540.KQ", 1, 300000)["cost_currency"] == "KRW"

    def test_explicit_currency_respected(self, csv_path):
        assert add_position(csv_path, "AAPL", 1, 250000, cost_currency="KRW")["cost_currency"] == "KRW"

    def test_add_more_without_currency_matches_inferred(self, csv_path):
        add_position(csv_path, "AAPL", 10, 150.0, cost_currency="USD")
        result = add_position(csv_path, "AAPL", 5, 160.0)
        assert result["shares"] == 15
        assert result["cost_currency"] == "USD"

    def test_mismatch_still_rejected(self, csv_path):
        add_position(csv_path, "AAPL", 10, 150.0)
        with pytest.raises(ValueError, match="cost_currency mismatch"):
            add_position(csv_path, "AAPL", 5, 200000, cost_currency="KRW")


class TestLoadPortfolioCurrencyInference:
    def test_blank_currency_inferred_from_symbol(self, tmp_path):
        path = tmp_path / "portfolio.csv"
        path.write_text(
            _HEADER + "AAPL,3,180.5,,,,,,,,,\n005930.KS,10,72000,,,,,,,,,\n",
            encoding="utf-8",
        )
        rows = {r["symbol"]: r for r in load_portfolio(str(path))}
        assert rows["AAPL"]["cost_currency"] == "USD"
        assert rows["005930.KS"]["cost_currency"] == "KRW"
