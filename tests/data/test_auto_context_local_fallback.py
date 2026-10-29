"""Tests for KIK-719: Local data/ fallback in get_context() when Neo4j is offline.

Verifies that conviction notes (e.g. 035420.KS thesis) and PF context can be
constructed from local files only.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.context.auto_context import get_context
from src.data.context.fallback_context import (
    build_portfolio_context_local,
    build_symbol_context_local,
)


@pytest.fixture
def tmp_data_env(tmp_path, monkeypatch):
    """Set up a temporary data/ structure with notes and portfolio.

    note_manager._NOTES_DIR 는 "data/notes" 상대 경로이므로 cwd 를 tmp_path 로
    바꿔 resolve 시킨다. portfolio_io.load_portfolio 는 경로를 명시하지 않으면
    DEFAULT_CSV_PATH 를 쓰므로 그것도 tmp_path 아래로 설정한다.
    """
    data_dir = tmp_path / "data"
    notes_dir = data_dir / "notes"
    notes_dir.mkdir(parents=True)
    portfolio_csv = data_dir / "portfolio.csv"
    watchlists_dir = data_dir / "watchlists"
    watchlists_dir.mkdir()
    screening_dir = data_dir / "screening_results"
    screening_dir.mkdir()

    # cwd 를 바꿔 상대 경로 "data/notes" 를 resolve 시킨다
    monkeypatch.chdir(tmp_path)
    # portfolio_io / fallback_context 의 절대 경로 참조를 덮어쓴다
    monkeypatch.setattr(
        "src.data.portfolio_io.DEFAULT_CSV_PATH", str(portfolio_csv),
    )
    monkeypatch.setattr(
        "src.data.context.fallback_context._SCREENING_DIR", str(screening_dir),
    )

    return {
        "notes_dir": notes_dir,
        "portfolio_csv": portfolio_csv,
        "watchlists_dir": watchlists_dir,
        "screening_dir": screening_dir,
    }


def _write_note(notes_dir: Path, symbol: str, ntype: str, content: str,
                date: str = "2026-04-25", source: str = "manual"):
    fp = notes_dir / f"{date}_{symbol.replace('.', '_')}_{ntype}.json"
    fp.write_text(
        json.dumps([{
            "id": f"note_{date}_{symbol}",
            "date": date,
            "symbol": symbol,
            "type": ntype,
            "content": content,
            "source": source,
        }], ensure_ascii=False),
        encoding="utf-8",
    )


def _write_portfolio(csv_path: Path, symbols: list[str]):
    header = (
        "symbol,shares,cost_price,cost_currency,purchase_date,memo,"
        "next_earnings,div_yield,buyback_yield,total_return,beta,role\n"
    )
    rows = "\n".join(
        f"{s},10,72000,KRW,2026-01-01,,,,,,," for s in symbols
    )
    csv_path.write_text(header + rows + "\n", encoding="utf-8")


# ===================================================================
# build_symbol_context_local
# ===================================================================

class TestBuildSymbolContextLocal:
    def test_conviction_thesis_detected(self, tmp_data_env):
        """035420.KS 의 thesis 에 "홀드확정" → conviction 플래그가 선다."""
        _write_note(
            tmp_data_env["notes_dir"], "035420.KS", "thesis",
            "[홀드확정 4/25] NAVER는 팔지 않는다",
            source="user-conviction+3llm-review",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["035420.KS"])

        result = build_symbol_context_local("035420.KS")
        assert result is not None
        md = result["context_markdown"]
        assert "conviction" in md.lower() or "홀드확정" in md
        assert "보유 중" in md
        assert result["relationship"] == "보유(conviction)"

    def test_unknown_symbol_returns_none(self, tmp_data_env):
        """notes/portfolio/watchlist/screening 에 없는 종목 → None."""
        result = build_symbol_context_local("UNKNOWN")
        assert result is None

    def test_held_no_conviction(self, tmp_data_env):
        """보유 중이지만 conviction 없음 → 일반 보유 relationship."""
        _write_portfolio(tmp_data_env["portfolio_csv"], ["AAPL"])
        result = build_symbol_context_local("AAPL")
        assert result is not None
        assert result["relationship"] == "보유"
        assert result["recommended_skill"] == "health"

    def test_concern_note_detected(self, tmp_data_env):
        """concern 메모 있음, 비보유 → relationship='우려있음'."""
        _write_note(
            tmp_data_env["notes_dir"], "TSLA", "concern", "수요 둔화",
        )
        result = build_symbol_context_local("TSLA")
        assert result is not None
        assert result["relationship"] == "우려있음"
        assert "concern" in result["context_markdown"]

    def test_screening_history_detected(self, tmp_data_env):
        """screening_results 에 3회 이상 출현 → 주목 종목."""
        for i in range(3):
            fp = tmp_data_env["screening_dir"] / f"trending_us_2026{i:02d}.json"
            fp.write_text(
                json.dumps({"results": [{"symbol": "NVDA", "score": 90}]}),
                encoding="utf-8",
            )
        result = build_symbol_context_local("NVDA")
        assert result is not None
        assert result["relationship"] == "주목 종목"
        assert "스크리닝 이력: 3건" in result["context_markdown"]

    def test_screening_below_threshold_returns_unknown(self, tmp_data_env):
        """screening_results 1-2건 → threshold 미만이라 미지 취급."""
        for i in range(2):
            fp = tmp_data_env["screening_dir"] / f"x_{i}.json"
            fp.write_text(
                json.dumps({"results": [{"symbol": "TSLA", "score": 80}]}),
                encoding="utf-8",
            )
        result = build_symbol_context_local("TSLA")
        # 2건뿐이고 다른 signal 없음 → relationship 은 "미지" (screen_count 는 포함됨)
        assert result is not None
        assert result["relationship"] == "미지"

    def test_conviction_keyword_uppercase(self, tmp_data_env):
        """대문자 'CONVICTION' 도 검출된다 (case-insensitive)."""
        _write_note(
            tmp_data_env["notes_dir"], "AAPL", "thesis",
            "Strong CONVICTION buy thesis",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["AAPL"])
        result = build_symbol_context_local("AAPL")
        assert result is not None
        assert result["relationship"] == "보유(conviction)"

    def test_screening_with_broken_json(self, tmp_data_env):
        """screening_results 에 JSON 손상 파일 → skip 하고 계속."""
        (tmp_data_env["screening_dir"] / "broken.json").write_text(
            "{invalid json", encoding="utf-8",
        )
        # Should not crash, just skip the broken file
        _write_portfolio(tmp_data_env["portfolio_csv"], ["NVDA"])
        result = build_symbol_context_local("NVDA")
        assert result is not None  # found via portfolio


# ===================================================================
# build_portfolio_context_local
# ===================================================================

class TestBuildPortfolioContextLocal:
    def test_empty_portfolio(self, tmp_data_env):
        """portfolio.csv 가 비어 있음 → 빈 컨텍스트 반환."""
        _write_portfolio(tmp_data_env["portfolio_csv"], [])
        result = build_portfolio_context_local()
        assert result["recommended_skill"] == "health"
        assert "보유 종목" not in result["context_markdown"]

    def test_with_holdings(self, tmp_data_env):
        """보유 종목 수 + 주요 메모가 포함된다."""
        _write_portfolio(tmp_data_env["portfolio_csv"], ["035420.KS", "NFLX"])
        _write_note(
            tmp_data_env["notes_dir"], "035420.KS", "thesis",
            "홀드확정",
        )
        result = build_portfolio_context_local()
        md = result["context_markdown"]
        assert "보유 종목: 2건" in md
        assert "[035420.KS] thesis" in md


# ===================================================================
# get_context() integration with fallback
# ===================================================================

class TestGetContextLocalFallback:
    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context.graph_store")
    def test_symbol_falls_back_to_local(self, mock_gs, mock_vs, tmp_data_env):
        """Neo4j 미접속 → 로컬 data/ 에서 conviction 종목을 읽는다."""
        mock_gs._get_driver.return_value = None
        mock_gs.is_available.return_value = False

        _write_note(
            tmp_data_env["notes_dir"], "035420.KS", "thesis",
            "[홀드확정] 팔지 않음",
            source="user-conviction",
        )
        _write_portfolio(tmp_data_env["portfolio_csv"], ["035420.KS"])

        result = get_context("035420.KS")
        assert result is not None
        assert "홀드확정" in result["context_markdown"]

    @patch("src.data.context.auto_context._load_lessons", return_value=[])
    @patch("src.data.context.auto_context._vector_search", return_value=[])
    @patch("src.data.context.auto_context.graph_store")
    def test_pf_query_falls_back_to_local(self, mock_gs, mock_vs, mock_les,
                                            tmp_data_env):
        """Neo4j 미접속 → 로컬 data/ 에서 PF 컨텍스트를 조립한다."""
        mock_gs._get_driver.return_value = None
        mock_gs.is_available.return_value = False

        _write_portfolio(
            tmp_data_env["portfolio_csv"], ["AAPL", "MSFT"],
        )
        _write_note(
            tmp_data_env["notes_dir"], "AAPL", "thesis", "AI 수요 지속",
        )

        result = get_context("PF 괜찮아?")
        assert result is not None
        md = result["context_markdown"]
        assert "보유 종목: 2건" in md
        assert "[AAPL]" in md
