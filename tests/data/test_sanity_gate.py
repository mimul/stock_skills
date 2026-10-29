"""src.data.sanity_gate 테스트 (KIK-734)."""

from __future__ import annotations

import pytest

from src.data.sanity_gate import (
    SanityGateError,
    assert_pf_complete,
    assert_lot_size,
    assert_conviction_respected,
    run_all_gates,
)


# ---------------------------------------------------------------------------
# 게이트 1: assert_pf_complete
# ---------------------------------------------------------------------------


class TestAssertPfComplete:
    def test_passes_with_valid_cash(self):
        assert_pf_complete(59_000_000.0, {"total_krw": 8_709_690})

    def test_raises_when_cash_is_none(self):
        with pytest.raises(SanityGateError, match="cash_balance.json 미참조"):
            assert_pf_complete(59_000_000.0, None)

    def test_raises_when_cash_missing_total_krw(self):
        with pytest.raises(SanityGateError, match="total_krw 필요"):
            assert_pf_complete(59_000_000.0, {"breakdown": {}})

    def test_raises_when_cash_negative(self):
        with pytest.raises(SanityGateError, match="cash 잔고가 음수"):
            assert_pf_complete(59_000_000.0, {"total_krw": -100})

    def test_raises_when_total_zero_or_negative(self):
        with pytest.raises(SanityGateError, match="PF 총자산이 0 이하"):
            assert_pf_complete(0, {"total_krw": 0})

    def test_passes_with_only_cash(self):
        # 주식이 없어도 현금이 있으면 통과
        assert_pf_complete(0.0, {"total_krw": 10_000_000})


# ---------------------------------------------------------------------------
# 게이트 2: assert_lot_size
# ---------------------------------------------------------------------------


class TestAssertLotSize:
    def test_korean_stock_any_positive_integer_passes(self):
        # 한국 주식은 1주 단위
        assert_lot_size("005930.KS", 1)
        assert_lot_size("005930.KS", 7)
        assert_lot_size("247540.KQ", 13)

    def test_us_single_share_passes(self):
        assert_lot_size("AAPL", 1)
        assert_lot_size("NVDA", 7)

    def test_zero_or_negative_fails(self):
        with pytest.raises(SanityGateError, match="양의 정수"):
            assert_lot_size("AAPL", 0)
        with pytest.raises(SanityGateError, match="양의 정수"):
            assert_lot_size("005930.KS", -5)

    def test_empty_symbol_fails(self):
        with pytest.raises(SanityGateError, match="symbol"):
            assert_lot_size("", 100)

    def test_float_shares_rejected(self):
        # KIK-734 리뷰: 정수 필수
        with pytest.raises(SanityGateError, match="int 필수"):
            assert_lot_size("AAPL", 1.5)
        with pytest.raises(SanityGateError, match="int 필수"):
            assert_lot_size("005930.KS", 100.0)

    def test_bool_shares_rejected(self):
        # bool 은 int 의 서브클래스지만 shares 로 허용하지 않는다
        with pytest.raises(SanityGateError, match="int 필수"):
            assert_lot_size("AAPL", True)

    def test_lot_size_gt_one_enforced(self, monkeypatch):
        # 매매 단위가 1보다 큰 시장이 추가될 경우를 대비한 분기 검증
        monkeypatch.setattr("src.data.sanity_gate.get_lot_size", lambda s: 100)
        with pytest.raises(SanityGateError, match="100주 단위"):
            assert_lot_size("XXX", 50)
        assert_lot_size("XXX", 200)


# ---------------------------------------------------------------------------
# 게이트 3: assert_conviction_respected
# ---------------------------------------------------------------------------


class TestAssertConvictionRespected:
    def test_buy_passes_for_conviction(self):
        # buy 는 conviction 종목에도 허용
        assert_conviction_respected("buy", "035420.KS", ["035420.KS", "AMZN"])

    def test_hold_passes(self):
        assert_conviction_respected("hold", "035420.KS", ["035420.KS"])

    def test_sell_conviction_fails(self):
        with pytest.raises(SanityGateError, match="conviction 종목"):
            assert_conviction_respected("sell", "035420.KS", ["035420.KS"])

    def test_trim_conviction_fails(self):
        with pytest.raises(SanityGateError, match="conviction 종목"):
            assert_conviction_respected("trim", "035420.KS", ["035420.KS"])

    def test_korean_action_keyword_blocked(self):
        with pytest.raises(SanityGateError, match="conviction 종목"):
            assert_conviction_respected("매도", "035420.KS", ["035420.KS"])
        with pytest.raises(SanityGateError, match="conviction 종목"):
            assert_conviction_respected("비중축소", "035420.KS", ["035420.KS"])

    def test_non_conviction_sell_passes(self):
        assert_conviction_respected("sell", "AMZN", ["035420.KS"])

    def test_empty_convictions_passes(self):
        assert_conviction_respected("sell", "035420.KS", [])


# ---------------------------------------------------------------------------
# 일괄: run_all_gates
# ---------------------------------------------------------------------------


class TestRunAllGates:
    def test_all_pass(self):
        run_all_gates(
            positions_value_krw=59_000_000,
            cash={"total_krw": 8_709_690},
            proposed_actions=[("sell", "AMZN", 10), ("buy", "005930.KS", 3)],
            convictions=["035420.KS"],
        )

    def test_pf_complete_failure_aborts(self):
        with pytest.raises(SanityGateError):
            run_all_gates(
                positions_value_krw=59_000_000,
                cash=None,
                proposed_actions=[("sell", "AMZN", 10)],
                convictions=[],
            )

    def test_conviction_violation_aborts(self):
        with pytest.raises(SanityGateError, match="conviction"):
            run_all_gates(
                positions_value_krw=59_000_000,
                cash={"total_krw": 8_709_690},
                proposed_actions=[("trim", "035420.KS", 5)],
                convictions=["035420.KS"],
            )

    def test_invalid_shares_aborts(self):
        with pytest.raises(SanityGateError, match="양의 정수"):
            run_all_gates(
                positions_value_krw=59_000_000,
                cash={"total_krw": 8_709_690},
                proposed_actions=[("sell", "005930.KS", 0)],
                convictions=[],
            )

    def test_malformed_action_aborts(self):
        with pytest.raises(SanityGateError, match="형식"):
            run_all_gates(
                positions_value_krw=59_000_000,
                cash={"total_krw": 8_709_690},
                proposed_actions=[("sell",)],
            )

    def test_no_actions_passes(self):
        # actions=None 이어도 cash 검사는 수행된다
        run_all_gates(
            positions_value_krw=59_000_000,
            cash={"total_krw": 8_709_690},
        )
