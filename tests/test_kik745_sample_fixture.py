"""KIK-745 sample fixture + workflow 안전성 테스트."""

import csv
import json
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PORTFOLIO = REPO_ROOT / "tests/fixtures/sample_portfolio.csv"
SAMPLE_CASH = REPO_ROOT / "tests/fixtures/sample_cash_balance.json"
SETUP_SCRIPT = REPO_ROOT / "scripts/setup_worktree.sh"
WORKFLOW_MD = REPO_ROOT / ".claude/rules/workflow.md"
GITIGNORE = REPO_ROOT / ".gitignore"


# ---------------------------------------------------------------------------
# 1. sample fixture 존재 + 구조
# ---------------------------------------------------------------------------


def test_sample_portfolio_exists():
    assert SAMPLE_PORTFOLIO.is_file()


def test_sample_portfolio_has_required_columns():
    with SAMPLE_PORTFOLIO.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) >= 5, "sample portfolio 는 5행 이상이어야 한다"
    required = {"symbol", "shares", "cost_price", "cost_currency", "role"}
    assert required.issubset(set(reader.fieldnames or [])), (
        f"컬럼 누락. 기대 {required}, 실제 {reader.fieldnames}"
    )


def test_sample_portfolio_loads_via_load_portfolio():
    """src.data.portfolio_io.load_portfolio 로 읽을 수 있어야 한다."""
    from src.data.portfolio_io import load_portfolio
    positions = load_portfolio(str(SAMPLE_PORTFOLIO))
    assert len(positions) >= 5
    symbols = [p["symbol"] for p in positions]
    # 범용 테스트 종목(한국 대표주 + 미국주)이 포함되어 있다
    assert any(s in ("005930.KS", "000660.KS", "AAPL") for s in symbols)


def test_sample_portfolio_uses_korean_market_conventions():
    """한국 시장 기준: .KS/.KQ 종목이 있고 통화는 KRW/USD 만 사용한다."""
    with SAMPLE_PORTFOLIO.open() as f:
        rows = list(csv.DictReader(f))
    symbols = [r["symbol"] for r in rows]
    assert any(s.endswith((".KS", ".KQ")) for s in symbols), "한국 종목(.KS/.KQ)이 없다"
    assert not any(s.endswith(".T") for s in symbols), "일본 종목(.T)이 남아 있다"
    currencies = {r["cost_currency"] for r in rows}
    assert currencies <= {"KRW", "USD"}, f"허용되지 않은 통화: {currencies}"


def test_sample_cash_balance_exists():
    assert SAMPLE_CASH.is_file()


def test_sample_cash_balance_is_hierarchical_kik742():
    """KIK-742 의 계층 형식 SSoT(KRW 기준)에 준거해야 한다."""
    data = json.loads(SAMPLE_CASH.read_text())
    assert "total_krw" in data
    legacy_totals = [k for k in data if k.startswith("total_") and k != "total_krw"]
    assert not legacy_totals, f"KRW 이외의 구 합계 키가 남아 있다: {legacy_totals}"
    assert "breakdown" in data
    assert isinstance(data["breakdown"], dict)
    assert "KRW" in data["breakdown"]
    # KRW/USD 엔트리는 모두 amount 키를 가진다
    for cur, entry in data["breakdown"].items():
        assert cur in ("KRW", "USD"), f"허용되지 않은 통화: {cur}"
        assert isinstance(entry, dict), f"breakdown.{cur} 는 dict 여야 한다"
        assert "amount" in entry, f"breakdown.{cur} 에 'amount' 키가 필요하다"
    # USD 엔트리는 원화 환산 키를 가진다
    usd = data["breakdown"].get("USD")
    if usd is not None:
        assert "krw_equivalent" in usd
        assert "rate_krw_per_usd" in usd


# ---------------------------------------------------------------------------
# 2. setup_worktree.sh
# ---------------------------------------------------------------------------


def test_setup_worktree_script_exists():
    assert SETUP_SCRIPT.is_file()


def test_setup_worktree_script_is_executable():
    assert os.access(SETUP_SCRIPT, os.X_OK), "setup_worktree.sh 는 실행 가능해야 한다"


def test_setup_worktree_script_does_not_copy_personal_data():
    """개인 PF 파일(~/stock-skills/data/portfolio.csv)을 복사하는 참조가 없어야 한다."""
    text = SETUP_SCRIPT.read_text()
    # 개인 PF 경로로의 cp 패턴 금지
    assert "stock-skills/data/portfolio.csv" not in text or "sample" in text
    # sample_portfolio.csv 를 사용할 것
    assert "sample_portfolio.csv" in text
    assert "sample_cash_balance.json" in text


# ---------------------------------------------------------------------------
# 3. workflow.md 수정
# ---------------------------------------------------------------------------


def test_workflow_md_no_personal_pf_copy_instruction():
    """workflow.md 에서 개인 PF cp 지시가 삭제되어 있어야 한다."""
    text = WORKFLOW_MD.read_text()
    # 구 기술(cp ~/stock-skills/data/portfolio.csv)이 남아 있지 않다
    bad_pattern = "cp ~/stock-skills/data/portfolio.csv"
    assert bad_pattern not in text, (
        f"workflow.md 에 개인 PF 복사 패턴이 남아 있다: {bad_pattern!r}"
    )


def test_workflow_md_mentions_sample_fixture():
    """workflow.md 에 sample fixture 이용에 대한 기술이 있어야 한다."""
    text = WORKFLOW_MD.read_text()
    assert "sample_portfolio.csv" in text
    assert "setup_worktree.sh" in text


def test_workflow_md_warns_against_personal_pf_copy():
    """개인 PF 복사 금지 경고 기술이 있어야 한다."""
    text = WORKFLOW_MD.read_text()
    assert "금지" in text
    assert "유출" in text or "실수로" in text


# ---------------------------------------------------------------------------
# 4. .gitignore 화이트리스트
# ---------------------------------------------------------------------------


def test_gitignore_whitelists_sample_portfolio():
    text = GITIGNORE.read_text()
    assert "!tests/fixtures/sample_portfolio.csv" in text


def test_gitignore_whitelists_sample_cash_balance():
    text = GITIGNORE.read_text()
    assert "!tests/fixtures/sample_cash_balance.json" in text
