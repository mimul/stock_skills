"""GraphRAG Tool — Neo4j 지식 그래프 파사드.

tools/ 층은 저장·조회만 담당한다. 판단 로직은 포함하지 않는다.
src/data/graph_store/ 와 src/data/graph_query/ 의 순수 함수를 re-export 한다.
Neo4j 미접속 시 graceful degradation(각 함수가 빈 값을 반환).
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# --- 조회 계열 (graph_query) ---
try:
    from src.data.graph_query import (  # noqa: E402
        get_prior_report,
        get_screening_frequency,
        get_trade_context,
        get_report_trend,
        get_research_chain,
        get_stock_news_history,
        get_sentiment_trend,
        get_catalysts,
        get_current_holdings,
        get_holdings_notes,
        get_stress_test_history,
        get_forecast_history,
        get_recent_market_context,
        get_upcoming_events,
        get_theme_trends,
        get_communities,
        get_stock_community,
        get_community_lessons,
    )
    HAS_GRAPH_QUERY = True
except ImportError:
    HAS_GRAPH_QUERY = False

# --- 저장 계열 (graph_store) ---
try:
    from src.data.graph_store import (  # noqa: E402
        get_stock_history,
        merge_note,
        merge_trade,
        merge_report,
        merge_screen,
        get_open_action_items,
    )
    HAS_GRAPH_STORE = True
except ImportError:
    HAS_GRAPH_STORE = False

# --- 컨텍스트 (auto_context) ---
try:
    from src.data.context import get_context  # noqa: E402
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False

# --- 일괄 동기화 (KIK-712) ---


def sync_all() -> dict:
    """data/ → GraphRAG 일괄 동기화.

    SKILL.md 의 「sync 해줘」에 대응하는 편의 함수.
    Neo4j 미접속 시 조기 반환. 개별 파일 오류는 건너뛰고 계속 진행.

    Returns
    -------
    dict
        {"synced": [...], "failed": [...], "skipped": [...]}
    """
    import json
    import glob
    from datetime import datetime

    result = {"synced": [], "failed": [], "skipped": []}

    # Neo4j 접속 확인
    try:
        from src.data.graph_store._common import is_available
        if not is_available():
            return {"synced": [], "failed": [], "skipped": ["Neo4j 미접속"]}
    except ImportError:
        return {"synced": [], "failed": [], "skipped": ["graph_store 미설치"]}

    # 1. Portfolio sync
    try:
        from src.data.portfolio_io import load_portfolio, DEFAULT_CSV_PATH
        from src.data.graph_store.portfolio import sync_portfolio
        holdings = load_portfolio(DEFAULT_CSV_PATH)
        if holdings:
            sync_portfolio(holdings)
            result["synced"].append(f"portfolio({len(holdings)}종목)")
    except Exception as e:
        result["failed"].append(f"portfolio: {e}")

    # 2. Notes sync (data/notes/*.json)
    try:
        from src.data.graph_store.note import merge_note as _merge_note
        notes_dir = Path(_project_root) / "data" / "notes"
        if notes_dir.exists():
            note_files = sorted(notes_dir.glob("*.json"))
            synced_count = 0
            for nf in note_files:
                try:
                    with open(nf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # note_manager saves as list [{...}], handle both formats
                    note = data[0] if isinstance(data, list) else data
                    if not note:
                        continue
                    _merge_note(
                        note_id=note.get("id", nf.stem),
                        note_date=note.get("date", ""),
                        note_type=note.get("type", "observation"),
                        content=note.get("content", ""),
                        symbol=note.get("symbol"),
                        source=note.get("source", "claude"),
                        category=note.get("category", ""),
                    )
                    synced_count += 1
                except Exception:
                    result["failed"].append(f"note: {nf.name}")
            if synced_count:
                result["synced"].append(f"notes({synced_count}건)")
    except Exception as e:
        result["failed"].append(f"notes: {e}")

    # 3. Update sync_status.yaml
    try:
        status_path = Path(_project_root) / "data" / "sync_status.yaml"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        status = {"last_sync": datetime.now().isoformat()}
        with open(status_path, "w", encoding="utf-8") as f:
            yaml.dump(status, f)
        result["synced"].append("sync_status 갱신")
    except Exception:
        pass  # non-critical

    return result


__all__ = [
    # 조회 계열
    "get_prior_report",
    "get_screening_frequency",
    "get_trade_context",
    "get_report_trend",
    "get_research_chain",
    "get_stock_news_history",
    "get_sentiment_trend",
    "get_catalysts",
    "get_current_holdings",
    "get_holdings_notes",
    "get_stress_test_history",
    "get_forecast_history",
    "get_recent_market_context",
    "get_upcoming_events",
    "get_theme_trends",
    "get_communities",
    "get_stock_community",
    "get_community_lessons",
    # 저장 계열
    "get_stock_history",
    "merge_note",
    "merge_trade",
    "merge_report",
    "merge_screen",
    "get_open_action_items",
    # 컨텍스트
    "get_context",
    # 동기화
    "sync_all",
    # 플래그
    "HAS_GRAPH_QUERY",
    "HAS_GRAPH_STORE",
    "HAS_CONTEXT",
]
