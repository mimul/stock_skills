"""KIK-746 dry-run 오케스트레이터 테스트."""

import os
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. verify_routing
# ---------------------------------------------------------------------------


def test_verify_routing_known_intent():
    from src.orchestrator import verify_routing
    r = verify_routing("좋은 주식 있어?")
    assert r.passed
    assert "screener" in r.agents
    # 기대 툴에 screen_stocks 가 포함된다
    assert any("screen" in t for t in r.expected_tools)


def test_verify_routing_chain_intent():
    from src.orchestrator import verify_routing
    r = verify_routing("이 종목 팔아야 해?")
    assert r.passed
    # 연쇄: risk-assessor → health-checker → strategist
    assert len(r.agents) >= 2
    assert "strategist" in r.agents


def test_verify_routing_unknown_intent_fails():
    from src.orchestrator import verify_routing
    r = verify_routing("@@@unknownXYZ123@@@")
    assert not r.passed
    assert any("no matching" in e for e in r.errors)


def test_verify_routing_returns_header_for_chain():
    from src.orchestrator import verify_routing
    r = verify_routing("이 종목 팔아야 해?")
    # routing.yaml 에 header 가 적혀 있다
    assert r.header is not None and "→" in r.header


def test_verify_routing_no_llm_calls(monkeypatch):
    """LLM API key 를 전부 삭제해도 dry-run 은 동작한다 (API 를 호출하지 않는 증거)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    from src.orchestrator import verify_routing
    r = verify_routing("좋은 주식 있어?")
    assert r.passed  # 통과 = LLM/Web 을 호출하지 않았다


def test_verify_routing_action_direct():
    """action: direct 패턴도 적절히 처리된다."""
    from src.orchestrator import verify_routing
    r = verify_routing("메모해줘")
    assert r.passed
    # action 플래그가 선다
    assert r.flags.get("action") == "direct"


# ---------------------------------------------------------------------------
# 2. verify_routing_yaml_integrity
# ---------------------------------------------------------------------------


def test_routing_yaml_integrity_passes_currently():
    """현재 routing.yaml 은 중복/누락 없이 PASS."""
    from src.orchestrator import verify_routing_yaml_integrity
    report = verify_routing_yaml_integrity()
    assert report["passed"], (
        f"routing.yaml integrity FAILED: {report['errors']}"
    )


def test_routing_yaml_integrity_detects_intent_dup(tmp_path):
    """의도적으로 중복 intent 를 넣으면 FAIL 한다."""
    from src.orchestrator import verify_routing_yaml_integrity

    bad = tmp_path / "routing.yaml"
    bad.write_text(yaml.safe_dump({
        "agents": {
            "screener": {"role": "test", "triggers": []},
        },
        "examples": [
            {"intent": "test_intent", "agent": "screener"},
            {"intent": "test_intent", "agent": "screener"},  # ← 중복
        ],
    }))
    report = verify_routing_yaml_integrity(routing_path=bad)
    assert not report["passed"]
    assert any("duplicate" in e for e in report["errors"])


def test_routing_yaml_integrity_detects_missing_agent(tmp_path):
    """존재하지 않는 agent 를 참조하면 FAIL 한다."""
    from src.orchestrator import verify_routing_yaml_integrity

    bad = tmp_path / "routing.yaml"
    bad.write_text(yaml.safe_dump({
        "agents": {},
        "examples": [
            {"intent": "test", "agent": "nonexistent-agent-xyz"},
        ],
    }))
    report = verify_routing_yaml_integrity(routing_path=bad)
    assert not report["passed"]
    assert any("nonexistent-agent-xyz" in e for e in report["errors"])


# ---------------------------------------------------------------------------
# 3. run_e2e.py --dry-run CLI
# ---------------------------------------------------------------------------


def test_run_e2e_dry_run_cli(monkeypatch):
    """run_e2e.py --dry-run 이 import + 실행 가능하다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    import sys
    sys.path.insert(0, str(REPO_ROOT))
    # 직접 import & 함수 호출
    from tests.e2e.run_e2e import run_dry_run
    success = run_dry_run()
    assert success, "dry-run must pass with current routing.yaml"
