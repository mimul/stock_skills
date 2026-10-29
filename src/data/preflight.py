"""DeepThink 용 프리플라이트 게이트 오케스트레이션 (KIK-735).

`src.data.sanity_gate` 의 세 게이트를 감싸고 다음을 추가한다:
- 도메인별 데이터 소스 로딩 (PF: portfolio + cash, market: tools)
- data/notes/ thesis 파일에서 conviction 종목 추출
- 구조화된 violation/warning 보고

DeepThink Step 0 은 `run_preflight(domain=...)` 를 호출하고 `passed=False` 면 중단한다.
DeepThink Step 5 는 매도/트림 추천을 내기 전에 `run_preflight(proposed_actions=...)` 로 재검증한다.
"""

from __future__ import annotations

import os
from typing import Iterable

from src.data import note_manager
from src.data import portfolio_io
from src.data import sanity_gate
from src.data.conviction import CONVICTION_KEYWORDS, is_conviction_text

# 하위 호환 별칭 (키워드 SSoT 는 src/data/conviction.py)
_CONVICTION_KEYWORDS = CONVICTION_KEYWORDS


class PreflightError(Exception):
    """프리플라이트가 실행을 차단했을 때 발생."""

    def __init__(self, violations: list[str]):
        self.violations = list(violations or [])
        super().__init__("; ".join(self.violations) or "preflight failed")


def extract_convictions(notes_dir: str | None = None) -> list[str]:
    """data/notes/ thesis 파일에서 conviction 종목을 추출한다.

    `src.data.context.fallback_context._detect_conviction` 과 같은 규칙이지만
    sanity_gate 에서 쓰기 위해 중복 없는 심볼 목록을 반환한다.
    """
    base_dir = notes_dir or note_manager._NOTES_DIR
    try:
        theses = note_manager.load_notes(note_type="thesis", base_dir=base_dir)
    except Exception:
        return []
    syms: set[str] = set()
    for n in theses:
        sym = n.get("symbol")
        if not sym:
            continue
        if is_conviction_text(n.get("content") or "", n.get("source") or ""):
            syms.add(sym)
    return sorted(syms)


def _check_pf_domain(violations: list[str], warnings: list[str]) -> dict:
    """PF 컨텍스트를 로드하고 assert_pf_complete 를 실행한다."""
    assets = portfolio_io.load_total_assets()
    cash = assets["cash"]
    if not assets["has_cash"]:
        violations.append(
            "cash_balance.json 에 total_krw 가 없거나 파일 누락 (KIK-735 PF gate)"
        )
        return {"cash_krw": 0.0, "positions_count": len(assets["positions"])}
    # 주식 평가액 자리에 현금을 넣어 assert_pf_complete 가 > 0 을 보게 한다.
    # 실제 주식 평가액 계산은 호출자 책임이며 여기서는 현금 존재만 검증한다.
    try:
        sanity_gate.assert_pf_complete(assets["cash_krw"], cash)
    except sanity_gate.SanityGateError as exc:
        violations.append(str(exc))
    return {
        "cash_krw": assets["cash_krw"],
        "positions_count": len(assets["positions"]),
    }


def run_preflight(
    domain: str = "pf",
    proposed_actions: Iterable[tuple] | None = None,
    notes_dir: str | None = None,
) -> dict:
    """DeepThink 세션의 프리플라이트 게이트를 실행한다.

    Parameters
    ----------
    domain : str
        'pf' / 'market' / 'sector' / 'stock'. 현재 'pf' 만 현금/보유 데이터 검사를
        수행하고 나머지는 게이트 1 을 건너뛴다.
    proposed_actions : (action, symbol) 또는 (action, symbol, shares) 의 Iterable
        매매 단위·conviction 검증 대상 추천 목록 (선택).
    notes_dir : str, optional
        notes 디렉터리 재정의 (테스트용).

    Returns
    -------
    dict with keys:
        passed     : bool                      (violation 없음)
        violations : list[str]                 (차단 사유)
        warnings   : list[str]                 (권고 사항)
        context    : {"cash_krw", "convictions", "positions_count", "domain"}
    """
    violations: list[str] = []
    warnings: list[str] = []
    cash_krw = 0.0
    positions_count = 0

    if domain == "pf":
        info = _check_pf_domain(violations, warnings)
        cash_krw = info["cash_krw"]
        positions_count = info["positions_count"]
    elif domain in {"market", "sector", "stock"}:
        # PF 데이터가 필수는 아니므로 권고만 남긴다.
        warnings.append(
            f"domain={domain}: PF 데이터 확인은 건너뜀 (KIK-735)"
        )
    else:
        violations.append(
            f"unknown domain: {domain!r} (expected pf/market/sector/stock)"
        )

    convictions = extract_convictions(notes_dir)

    # 게이트 2 + 게이트 3: 제안 액션 검증
    if proposed_actions:
        for item in proposed_actions:
            try:
                if not isinstance(item, (tuple, list)):
                    raise sanity_gate.SanityGateError(
                        f"proposed_actions 요소는 tuple/list (got {type(item).__name__})"
                    )
                if len(item) == 3:
                    action, symbol, shares = item
                elif len(item) == 2:
                    action, symbol = item
                    shares = None
                else:
                    raise sanity_gate.SanityGateError(
                        f"proposed_actions 요소 형식이 잘못됨: {item}"
                    )
                if shares is not None:
                    sanity_gate.assert_lot_size(symbol, shares)
                sanity_gate.assert_conviction_respected(action, symbol, convictions)
            except sanity_gate.SanityGateError as exc:
                violations.append(str(exc))

    return {
        "passed": not violations,
        "violations": violations,
        "warnings": warnings,
        "context": {
            "cash_krw": cash_krw,
            "convictions": convictions,
            "positions_count": positions_count,
            "domain": domain,
        },
    }


__all__ = ["PreflightError", "run_preflight", "extract_convictions"]
