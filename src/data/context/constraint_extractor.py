"""Constraint extraction from investment lessons for plan-check flow (KIK-596).

Extracts action type from user query, loads relevant lessons,
and structures them as constraints for the multi-agent planning system.

Usage:
    from src.data.context.constraint_extractor import extract_constraints
    result = extract_constraints("035420.KS 매도하고 대신할 종목 찾아줘")
    # => {"action_type": "swap_proposal", "symbols": ["035420.KS"], "constraints": [...]}
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Action type classification
# ---------------------------------------------------------------------------

# 액션 유형별 판별 키워드 (한국어 + 영어). 부분 문자열 매칭이므로
# 조사·어미가 붙어도 어간이 포함되도록 짧은 형태로 둔다.
_ACTION_PATTERNS: dict[str, list[str]] = {
    "swap_proposal": [
        # "대신"/"대체"는 일반어("대체로", "대신증권")와 겹치므로 어미를 붙여 좁힌다
        "교체", "갈아타", "갈아탈", "스왑", "대신할", "대신 살", "대신에",
        "대체할", "대체 종목", "대체재", "리플레이스", "swap", "replace",
    ],
    "new_buy": [
        "사고 싶", "매수하고 싶", "매수할까", "진입", "엔트리",
        "추가하고 싶", "살까", "살지 고민", "추가 매수", "매수 검토",
        "매수", "사도 될", "사야 할", "사야 해",
    ],
    "sell": [
        "팔고 싶", "매도", "손절", "익절", "처분", "포지션 정리",
        "이익 실현", "이익실현", "팔까", "팔아야", "팔지",
    ],
    "rebalance": [
        "리밸런스", "리밸런싱", "배분 조정", "비중 조정", "밸런스 개선",
        "쏠림 조정",
    ],
    "adjust": [
        "조정", "조언", "처방", "고쳐", "개선해",
        "대책", "어떻게 해야", "어떻게 하면", "어떡해",
    ],
}

# 액션 유형별 lesson 매칭 보강 키워드
_ACTION_BOOST_KEYWORDS: dict[str, list[str]] = {
    "swap_proposal": [
        "교체", "통화배분", "지역분산", "매매단위", "what-if",
        "섹터", "빈자리",
    ],
    "new_buy": [
        "진입", "카탈리스트", "밸류에이션", "확신",
        "conviction", "타이밍",
    ],
    "sell": [
        "손절", "임계값", "카탈리스트", "테제", "EXIT",
    ],
    "rebalance": [
        "배분", "HHI", "집중", "분산", "쏠림",
    ],
    "adjust": [
        "헬스체크", "경고", "EXIT", "개선", "약점",
    ],
}


def classify_action_type(user_query: str) -> str:
    """Classify user query into an action type.

    Returns one of: swap_proposal, new_buy, sell, rebalance, adjust.
    Falls back to "adjust" if no pattern matches.
    """
    query_lower = user_query.lower()
    scores: dict[str, int] = {k: 0 for k in _ACTION_PATTERNS}

    for action_type, keywords in _ACTION_PATTERNS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                scores[action_type] += 1

    # 동점이면 _ACTION_PATTERNS 의 선언 순서(swap → new_buy → sell → rebalance → adjust)가 우선한다
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0:
        return "adjust"
    return best


# ---------------------------------------------------------------------------
# Constraint extraction
# ---------------------------------------------------------------------------


def extract_constraints(
    user_query: str,
    max_constraints: int = 5,
) -> dict:
    """Extract constraints from investment lessons for the given user query.

    Returns a dict with:
        action_type: str
        symbols: list[str]
        constraints: list[dict]  -- each has id, trigger, expected_action,
                                    source, community, relevance_score
        lesson_count: int
        matched_count: int
    """
    action_type = classify_action_type(user_query)
    symbols = _extract_symbols(user_query)

    # Load all lessons
    lessons = _load_lessons()
    lesson_count = len(lessons)

    # Build enriched query with action-type boost keywords
    enriched_query = _build_enriched_query(user_query, action_type)

    # Score and select relevant lessons
    relevant = _select_lessons(lessons, enriched_query, max_constraints)

    # Convert to constraint format
    constraints = [
        _lesson_to_constraint(les, score)
        for score, les in relevant
    ]

    # Auto-inject lot size constraints for detected symbols
    lot_constraints = _build_lot_size_constraints(symbols)
    constraints = lot_constraints + constraints

    return {
        "action_type": action_type,
        "symbols": symbols,
        "constraints": constraints,
        "lesson_count": lesson_count,
        "matched_count": len(constraints),
    }


def format_constraints_markdown(result: dict) -> str:
    """Format constraint extraction result as markdown."""
    lines = [
        f"## 제약 조건 ({result['action_type']})",
        "",
    ]
    if result["symbols"]:
        lines.append(f"대상 심볼: {', '.join(result['symbols'])}")
        lines.append("")

    if not result["constraints"]:
        lines.append("해당하는 lesson이 없습니다.")
        return "\n".join(lines)

    for i, c in enumerate(result["constraints"], 1):
        lines.append(
            f"### 제약{i}: {c['source']} ({c['community']}, "
            f"관련도{c['relevance_score']:.2f})"
        )
        lines.append(f"- **trigger**: {c['trigger']}")
        lines.append(f"- **expected_action**: {c['expected_action']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_lot_size_constraints(symbols: list[str]) -> list[dict]:
    """Auto-generate lot size constraints for detected symbols.

    매매 단위가 2주 이상인 심볼에 대해서만 구조적 제약을 주입한다.
    한국·미국 주식은 모두 1주 단위이므로 현재는 제약이 생성되지 않지만,
    API 호환을 위해 로직은 유지한다.
    """
    try:
        from src.data.ticker_utils import get_lot_size, infer_currency
    except ImportError:
        return []

    constraints = []
    for sym in symbols:
        lot = get_lot_size(sym)
        if lot <= 1:
            continue  # 한국·미국 주식: 1주 단위, 제약 불필요
        currency = infer_currency(sym)
        constraints.append({
            "id": f"system_lot_size_{sym}",
            "trigger": f"{sym} 매매 제안 시",
            "expected_action": (
                f"{sym}은(는) {lot}주 단위로만 매매할 수 있다. "
                f"일부 매도({lot}주 미만)는 불가능. "
                f"매수 시 {lot}주 x 주가({currency})가 예산 내인지 확인할 것"
            ),
            "source": f"[시스템 제약] {sym} 매매 단위={lot}주",
            "community": "시스템 제약",
            "relevance_score": 1.0,  # Always highest priority
        })
    return constraints


def _extract_symbols(user_query: str) -> list[str]:
    """Extract ticker symbols from user query."""
    try:
        from src.data.ticker_utils import extract_all_symbols
        return extract_all_symbols(user_query)
    except ImportError:
        return []


def _load_lessons() -> list[dict]:
    """Load all lesson-type notes."""
    try:
        from src.data.note_manager import load_notes
        return load_notes(note_type="lesson")
    except ImportError:
        return []


def _build_enriched_query(user_query: str, action_type: str) -> str:
    """Enrich user query with action-type specific keywords for better matching."""
    boost = _ACTION_BOOST_KEYWORDS.get(action_type, [])
    return f"{user_query} {' '.join(boost)}"


def _select_lessons(
    lessons: list[dict],
    enriched_query: str,
    max_results: int,
) -> list[tuple[float, dict]]:
    """Score and select relevant lessons using existing scoring logic.

    Returns list of (score, lesson) tuples sorted by relevance.
    """
    try:
        from src.data.lesson_conflict import keyword_similarity
    except ImportError:
        return [(0.0, les) for les in lessons[:max_results]]

    query_lower = enriched_query.lower()
    scored: list[tuple[float, dict]] = []

    for les in lessons:
        trigger = _get_trigger(les)
        expected = _get_action(les)
        symbol = (les.get("symbol") or "").strip()
        content = (les.get("content") or "")[:80].strip()
        les_text = f"{trigger} {expected} {symbol} {content}".strip()

        # Base keyword similarity (public API from lesson_conflict)
        score = keyword_similarity(query_lower, les_text.lower())

        # Bonus: symbol appears in query
        if symbol and symbol.lower() in query_lower:
            score += 0.3

        # Bonus: trigger substring match
        if trigger:
            trigger_lower = trigger.lower()
            for word in trigger_lower.split():
                if len(word) >= 2 and word in query_lower:
                    score += 0.2
                    break
            # 문자 단위 중복도 (어절 일치가 전혀 없을 때만 보조 점수로 사용.
            # 한국어는 조사가 붙어 어절 일치가 빗나갈 수 있어 부분 일치를 구제)
            if score < 0.1:
                common = sum(
                    1 for c in set(trigger_lower)
                    if c in query_lower and c not in " \t\n"
                )
                total = len(set(trigger_lower) | set(query_lower))
                if total > 0:
                    score += (common / total) * 0.3

        if score > 0:
            scored.append((score, les))

    scored.sort(key=lambda x: (x[0], x[1].get("date", "")), reverse=True)
    return scored[:max_results]


def _get_trigger(lesson: dict) -> str:
    """Extract trigger from lesson, with content fallback."""
    try:
        from src.data.lesson_conflict import extract_trigger
        return extract_trigger(lesson)
    except ImportError:
        return (lesson.get("trigger") or "").strip()


def _get_action(lesson: dict) -> str:
    """Extract expected_action from lesson, with content fallback."""
    try:
        from src.data.lesson_conflict import extract_action
        return extract_action(lesson)
    except ImportError:
        return (lesson.get("expected_action") or "").strip()


def _classify_community(lesson: dict) -> str:
    """Classify lesson into a community category."""
    try:
        from src.data.lesson_community import classify_lesson
        content = lesson.get("content", "")
        trigger = _get_trigger(lesson)
        return classify_lesson(content, trigger)
    except ImportError:
        return "기타"


def _lesson_to_constraint(lesson: dict, relevance_score: float) -> dict:
    """Convert a lesson to a constraint dict."""
    trigger = _get_trigger(lesson)
    expected_action = _get_action(lesson)
    content = (lesson.get("content") or "").strip()
    # Extract first line or first 60 chars as source label
    first_line = content.split("\n")[0][:60] if content else ""
    source = first_line or lesson.get("id", "unknown")

    return {
        "id": lesson.get("id", ""),
        "trigger": trigger,
        "expected_action": expected_action,
        "source": source,
        "community": _classify_community(lesson),
        "relevance_score": round(relevance_score, 2),
    }
