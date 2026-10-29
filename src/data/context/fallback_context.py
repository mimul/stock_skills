"""Local data/ fallback for get_context() when Neo4j is unavailable (KIK-719).

When Neo4j is not connected, build context_markdown from local files:
- data/notes/*.json (thesis/observation/concern via note_manager.load_notes)
- data/portfolio.csv (holding status via portfolio_io.load_portfolio)
- data/screening_results/*.json (past screening surfaces)

This module supports the conviction-violation detection pathway by ensuring
thesis notes (e.g. "홀드확정") are always readable without Neo4j.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from src.data import note_manager
from src.data import portfolio_io
from src.data.conviction import is_conviction_text


_SCREENING_DIR = "data/screening_results"  # relative; resolved at call time


def _is_held_local(symbol: str) -> bool:
    """Check holding status from data/portfolio.csv (Neo4j-free)."""
    try:
        portfolio = portfolio_io.load_portfolio(portfolio_io.DEFAULT_CSV_PATH)
    except Exception:
        return False
    sym_upper = symbol.upper()
    return any(
        (p.get("symbol") or "").upper() == sym_upper for p in portfolio
    )


_WATCHLIST_DIR = "data/watchlists"  # relative; resolved at call time


def _is_bookmarked_local(symbol: str) -> bool:
    """Check watchlist membership from data/watchlists/*.json (Neo4j-free).

    KIK-743: tools/watchlist.py:save_watchlist 는 list 형식(["AAPL", ...])으로
    저장하므로 list / dict {symbols: [...]} 두 형식을 모두 지원한다.
    """
    wl_dir = Path(_WATCHLIST_DIR)
    if not wl_dir.exists():
        return False
    sym_upper = symbol.upper()
    for fp in wl_dir.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        # KIK-743: list 직접 저장 형식 (tools/watchlist.py 의 표준 형식)
        if isinstance(data, list):
            symbols = data
        elif isinstance(data, dict):
            # legacy: {"symbols": [...]} 형식
            symbols = data.get("symbols")
        else:
            symbols = None
        if symbols and any(
            (s or "").upper() == sym_upper for s in symbols if isinstance(s, str)
        ):
            return True
    return False


def _count_screening_appearances(symbol: str) -> int:
    """Count how many past screening_results contain this symbol."""
    sd = Path(_SCREENING_DIR)
    if not sd.exists():
        return 0
    sym_upper = symbol.upper()
    count = 0
    for fp in sd.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        # Common shapes: {"results": [{"symbol": ...}]} or [{"symbol": ...}]
        items = data.get("results") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if (item.get("symbol") or "").upper() == sym_upper:
                count += 1
                break  # one count per file
    return count


def _detect_conviction(notes: list[dict]) -> Optional[str]:
    """Return conviction snippet if any note signals 'hold confirmed'.

    키워드 규칙은 src/data/conviction.py (preflight 와 공유) 를 따른다.
    """
    for n in notes:
        content = (n.get("content") or "")
        if is_conviction_text(content, n.get("source") or ""):
            return content[:120]
    return None


def _format_notes_section(notes: list[dict], limit: int = 5) -> list[str]:
    """Format thesis/observation/concern notes into markdown lines."""
    lines: list[str] = []
    if not notes:
        return lines
    lines.append("## 투자 메모")
    for n in notes[:limit]:
        ntype = n.get("type", "?")
        date = n.get("date", "")
        content = (n.get("content") or "")[:140]
        date_part = f" ({date})" if date else ""
        lines.append(f"- [{ntype}]{date_part} {content}")
    return lines


def build_symbol_context_local(symbol: str) -> Optional[dict]:
    """Build symbol context from local data/ when Neo4j is unavailable.

    Returns a dict matching get_context()'s shape, or None if no signals exist.
    """
    notes = note_manager.load_notes(symbol=symbol)
    is_held = _is_held_local(symbol)
    is_bookmarked = _is_bookmarked_local(symbol)
    screen_count = _count_screening_appearances(symbol)
    conviction = _detect_conviction(notes)

    # If we have nothing meaningful, return None (graceful degradation)
    if not notes and not is_held and not is_bookmarked and screen_count == 0:
        return None

    # Skill recommendation (simplified, Neo4j-free)
    if is_held:
        if conviction:
            skill, reason, relationship = (
                "health", "보유 + conviction 종목 → 헬스체크", "보유(conviction)",
            )
        else:
            skill, reason, relationship = (
                "health", "보유 종목 → 헬스체크 우선", "보유",
            )
    elif notes and any(n.get("type") == "concern" for n in notes):
        skill, reason, relationship = (
            "report", "우려 메모 있음 → 재검증", "우려있음",
        )
    elif is_bookmarked:
        skill, reason, relationship = (
            "report", "워치리스트 등록됨 → 리포트", "감시중",
        )
    elif screen_count >= 3:
        # Threshold aligned with Neo4j path's _recommend_skill (3+ screenings)
        skill, reason, relationship = (
            "report", f"스크리닝 {screen_count}회 출현 → 리포트", "주목 종목",
        )
    elif notes:
        skill, reason, relationship = (
            "report", "과거 메모 있음 → 리포트", "기존",
        )
    else:
        skill, reason, relationship = (
            "report", "미지의 종목 → 처음부터 조사", "미지",
        )

    # Compose markdown
    lines = [f"## 과거 이력: {symbol} ({relationship})"]
    if conviction:
        lines.append(f"- ⚠ conviction 종목: {conviction}")
    if is_held:
        lines.append("- 보유 중 (portfolio.csv)")
    if is_bookmarked:
        lines.append("- 워치리스트 등록")
    if screen_count > 0:
        lines.append(f"- 스크리닝 이력: {screen_count}건")
    lines.extend(_format_notes_section(notes))
    lines.append(f"\n**추천**: {skill} ({reason})")

    return {
        "symbol": symbol,
        "context_markdown": "\n".join(lines),
        "recommended_skill": skill,
        "recommendation_reason": reason,
        "relationship": relationship,
    }


def build_portfolio_context_local() -> dict:
    """Build portfolio context from data/portfolio.csv + data/notes (Neo4j-free)."""
    try:
        portfolio = portfolio_io.load_portfolio(portfolio_io.DEFAULT_CSV_PATH)
    except Exception:
        portfolio = []

    lines = ["## 포트폴리오 컨텍스트"]
    if portfolio:
        lines.append(f"- 보유 종목: {len(portfolio)}건")

    # Collect notes for held symbols (top 1 per symbol)
    held_notes_lines: list[str] = []
    for entry in portfolio:
        sym = entry.get("symbol")
        if not sym:
            continue
        notes = note_manager.load_notes(symbol=sym)
        # Prioritize thesis/concern over observation
        priority = {"thesis": 0, "concern": 1, "observation": 2, "review": 3}
        notes_sorted = sorted(
            notes, key=lambda n: priority.get(n.get("type", ""), 99),
        )
        for n in notes_sorted[:1]:
            ntype = n.get("type", "?")
            content = (n.get("content") or "")[:60]
            ndate = n.get("date", "")
            date_part = f" ({ndate})" if ndate else ""
            held_notes_lines.append(f"- [{sym}] {ntype}: {content}{date_part}")

    if held_notes_lines:
        lines.append("")
        lines.append("## 보유 종목 주요 메모")
        lines.extend(held_notes_lines)

    lines.append("\n**추천**: health (포트폴리오 진단)")

    return {
        "symbol": "",
        "context_markdown": "\n".join(lines),
        "recommended_skill": "health",
        "recommendation_reason": "포트폴리오 조회",
        "relationship": "PF",
    }
