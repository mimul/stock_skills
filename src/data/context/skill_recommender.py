"""Graph-state analysis and skill recommendation (KIK-411/414).

Examines a stock's history in the knowledge graph (trades, screens, notes,
health checks, researches) and recommends the best skill to run next.
"""

from src.data.context.freshness import _days_since


def _has_bought_not_sold(history: dict) -> bool:
    """Check if there are BOUGHT trades but no matching SOLD trades."""
    trades = history.get("trades", [])
    bought = [t for t in trades if t.get("type") == "buy"]
    sold = [t for t in trades if t.get("type") == "sell"]
    return len(bought) > 0 and len(sold) < len(bought)


def _screening_count(history: dict) -> int:
    """Count how many Screen nodes reference this stock."""
    return len(history.get("screens", []))


def _has_recent_research(history: dict, days: int = 7) -> bool:
    """Check if there's a Research within the given days."""
    for r in history.get("researches", []):
        if _days_since(r.get("date", "")) <= days:
            return True
    return False


def _has_exit_alert(history: dict) -> bool:
    """Check if latest health check had EXIT alert (via notes/health_checks)."""
    health_checks = history.get("health_checks", [])
    if not health_checks:
        return False
    notes = history.get("notes", [])
    for n in notes:
        if n.get("type") == "lesson" and _days_since(n.get("date", "")) <= 30:
            return True
    return False


def _thesis_needs_review(history: dict, days: int = 90) -> bool:
    """Check if a thesis note exists and is older than the given days."""
    notes = history.get("notes", [])
    for n in notes:
        if n.get("type") == "thesis" and _days_since(n.get("date", "")) >= days:
            return True
    return False


def _has_concern_notes(history: dict) -> bool:
    """Check if there are concern-type notes."""
    notes = history.get("notes", [])
    return any(n.get("type") == "concern" for n in notes)


def _recommend_skill(history: dict, is_bookmarked: bool,
                     is_held: bool = False) -> tuple[str, str, str]:
    """Determine recommended skill based on graph state.

    Returns (skill, reason, relationship).
    """
    # Priority order: higher = checked first
    # KIK-414: HOLDS relationship is authoritative for current holdings
    if is_held or _has_bought_not_sold(history):
        if _thesis_needs_review(history, 90):
            return ("health", "테제 3개월 경과 → 리뷰 권고", "보유(리뷰 필요)")
        return ("health", "보유 종목 → 헬스체크 우선", "보유")

    if _has_exit_alert(history):
        return ("screen_alternative", "EXIT 판정 → 대체 후보 검색", "EXIT판정")

    if is_bookmarked:
        return ("report", "워치 중 → 리포트 + 이전 대비 차분", "워치중")

    if _screening_count(history) >= 3:
        return ("report", "3회 이상 스크리닝 출현 → 주목 종목", "주목")

    if _has_recent_research(history, 7):
        return ("report_diff", "최근 리서치 있음 → 차분 모드", "리서치완료")

    if _has_concern_notes(history):
        return ("report", "우려 메모 있음 → 재검증", "우려있음")

    if history.get("screens") or history.get("reports") or history.get("trades"):
        return ("report", "과거 데이터 있음 → 리포트", "기존")

    return ("report", "미지의 종목 → 처음부터 조사", "미지")


def _check_bookmarked(symbol: str, _graph_store=None) -> bool:
    """Check if symbol is in any watchlist via Neo4j.

    Args:
        symbol: Ticker symbol to check.
        _graph_store: graph_store module (dependency injection for testability).
            When None, imports from src.data at call time.
    """
    if _graph_store is None:
        from src.data import graph_store as _graph_store
    driver = _graph_store._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (w:Watchlist)-[:BOOKMARKED]->(s:Stock {symbol: $symbol}) "
                "RETURN count(w) AS cnt",
                symbol=symbol,
            )
            record = result.single()
            return record["cnt"] > 0 if record else False
    except Exception:
        return False
