"""추천 생성 전 세이프티 게이트 (KIK-734).

에이전트가 매도/트림/매수 추천을 내기 전에 반드시 통과해야 하는 하드 assert.
자기 위반이 불가능하도록 게이트가 예외를 던져 추천이 사용자에게 도달하지 못하게 한다.

세 가지 게이트:
1. assert_pf_complete  — cash_balance.json 이 로드되어 있고 총자산 > 0
2. assert_lot_size     — 주식 수가 양의 정수이며 매매 단위(한국·미국 모두 1주)에 맞는지
3. assert_conviction_respected — conviction 종목에는 매도/트림 추천 금지
"""

from __future__ import annotations

from typing import Iterable, Mapping

from src.data.ticker_utils import get_lot_size


class SanityGateError(AssertionError):
    """세이프티 게이트가 추천을 차단했을 때 발생."""


# ---------------------------------------------------------------------------
# 게이트 1: PF 총자산 완전성
# ---------------------------------------------------------------------------


def assert_pf_complete(
    positions_value_krw: float,
    cash: Mapping | None,
) -> None:
    """PF 총자산 계산에 주식과 현금이 모두 포함됐는지 검증한다.

    Parameters
    ----------
    positions_value_krw : float
        주식 보유 평가액(KRW 환산)
    cash : Mapping | None
        cash_balance.json 로드 결과. None 이면 게이트 실패.

    Raises
    ------
    SanityGateError
        현금 미참조, 또는 PF 총자산이 0 이하
    """
    if cash is None:
        raise SanityGateError(
            "cash_balance.json 미참조. HC/Risk 기동 시 필수 입력 (KIK-734)"
        )
    if not isinstance(cash, Mapping) or "total_krw" not in cash:
        raise SanityGateError(
            "cash 구조가 잘못됨: total_krw 필요 (KIK-734)"
        )
    cash_krw = float(cash.get("total_krw") or 0)
    if cash_krw < 0:
        raise SanityGateError(f"cash 잔고가 음수: {cash_krw}")
    total = float(positions_value_krw or 0) + cash_krw
    if total <= 0:
        raise SanityGateError(f"PF 총자산이 0 이하: {total}")


# ---------------------------------------------------------------------------
# 게이트 2: 매매 단위 검증
# ---------------------------------------------------------------------------


def assert_lot_size(symbol: str, shares: int) -> None:
    """주식 수가 양의 정수이고 매매 단위의 배수인지 검증한다.

    한국(KOSPI/KOSDAQ)·미국 모두 1주 단위이므로 실질적으로는
    정수·양수 검증이 핵심이다. 매매 단위는 ticker_utils.get_lot_size 가 SSoT.
    """
    if not symbol:
        raise SanityGateError("symbol 이 비어 있음")
    # KIK-734 리뷰: 정수 필수 (float 이 통과하던 문제)
    if isinstance(shares, bool) or not isinstance(shares, int):
        raise SanityGateError(
            f"{symbol}: shares 는 int 필수 (got {type(shares).__name__}={shares})"
        )
    if shares <= 0:
        raise SanityGateError(f"{symbol}: shares 는 양의 정수 (got {shares})")
    lot = get_lot_size(symbol)
    if lot > 1 and shares % lot != 0:
        raise SanityGateError(
            f"{symbol}은(는) {lot}주 단위 (got {shares})"
        )


# ---------------------------------------------------------------------------
# 게이트 3: conviction 종목 보호
# ---------------------------------------------------------------------------


_SELL_LIKE_ACTIONS = frozenset({
    "sell", "trim", "exit", "close",
    "매도", "트림", "전량매도", "비중축소",
})


def assert_conviction_respected(
    action: str,
    symbol: str,
    convictions: Iterable[str],
) -> None:
    """conviction 종목에 매도/트림 추천이 나가지 않도록 검증한다.

    Parameters
    ----------
    action : str
        buy/hold/sell/trim/exit/close 중 하나 (또는 한국어 동의어)
    symbol : str
        대상 티커
    convictions : Iterable[str]
        conviction 종목 목록 (data/notes thesis 의 conviction 마커에서 로드)
    """
    if not action or not symbol:
        return
    if action.lower() in _SELL_LIKE_ACTIONS or action in _SELL_LIKE_ACTIONS:
        if symbol in set(convictions):
            raise SanityGateError(
                f"{symbol}은(는) conviction 종목. {action} 제안 금지 (KIK-734)"
            )


# ---------------------------------------------------------------------------
# 일괄 실행
# ---------------------------------------------------------------------------


def run_all_gates(
    *,
    positions_value_krw: float,
    cash: Mapping | None,
    proposed_actions: Iterable[tuple[str, str, int | None]] | None = None,
    convictions: Iterable[str] | None = None,
) -> None:
    """관련 게이트를 모두 실행한다.

    Parameters
    ----------
    positions_value_krw, cash : assert_pf_complete 참조
    proposed_actions : (action, symbol, shares|None) 의 Iterable
        각 제안에 대해 매매 단위와 conviction 보호를 검사한다.
    convictions : Iterable[str]
        conviction 종목 목록.
    """
    assert_pf_complete(positions_value_krw, cash)
    if proposed_actions:
        conv = list(convictions or [])
        for item in proposed_actions:
            if len(item) == 3:
                action, symbol, shares = item
            elif len(item) == 2:
                action, symbol = item
                shares = None
            else:
                raise SanityGateError(f"proposed_actions 요소 형식이 잘못됨: {item}")
            if shares is not None:
                assert_lot_size(symbol, shares)
            assert_conviction_respected(action, symbol, conv)


__all__ = [
    "SanityGateError",
    "assert_pf_complete",
    "assert_lot_size",
    "assert_conviction_respected",
    "run_all_gates",
]
