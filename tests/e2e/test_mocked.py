"""모의 E2E 테스트 (KIK-747).

LLM API / Yahoo Finance / Grok 을 전부 stub 화하고, 결정론적으로
agent.md / examples.yaml / orchestrator 의 동작을 검증한다.

이용 방침:
- agent.md / examples.yaml / routing.yaml 은 실물을 사용
- 외부 I/O 만 stub (tools/llm.py, tools/grok.py, tools/yahoo_finance.py)
- 개인 PF 는 건드리지 않는다 (tests/fixtures/sample_portfolio.csv 를 이용, KIK-745)
- 전 시나리오 10초 이내, API key 전부 삭제된 환경에서도 PASS
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PORTFOLIO = REPO_ROOT / "tests/fixtures/sample_portfolio.csv"
SAMPLE_CASH = REPO_ROOT / "tests/fixtures/sample_cash_balance.json"
STOCK_INFO_FIXTURE = REPO_ROOT / "tests/fixtures/stock_info.json"
STOCK_DETAIL_FIXTURE = REPO_ROOT / "tests/fixtures/stock_detail.json"

# 기본 샘플 종목 (치환표: 삼성전자 / SK하이닉스)
SAMPLE_SYMBOL = "005930.KS"
SAMPLE_SYMBOL_2 = "000660.KS"


# ---------------------------------------------------------------------------
# Mock fixtures (이 모듈에서 autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mocked_e2e_env(monkeypatch, tmp_path):
    """LLM / Yahoo Finance / Grok 을 stub 하고 실제 API 키를 비활성화한다.

    기존 `_block_external_io` (conftest.py) 는 Neo4j/TEI/Grok 을 다루므로,
    여기서는 추가로 LLM 과 Yahoo Finance 를 stub 한다.
    """
    # 1) API keys 삭제 (실호출을 물리적으로 막는 최종 방어선)
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    # 2) LLM stub
    def _stub_call_llm(provider, model, prompt, **kwargs):
        return f"[mock:{provider}] {prompt[:50]}... → 추천: {SAMPLE_SYMBOL} (PER 10.5)"

    monkeypatch.setattr("tools.llm.call_llm", _stub_call_llm)

    # 3) Yahoo Finance stub: fixtures 에서 반환
    stock_info = json.loads(STOCK_INFO_FIXTURE.read_text())
    stock_detail = json.loads(STOCK_DETAIL_FIXTURE.read_text())

    def _stub_get_stock_info(symbol):
        d = dict(stock_info)
        d["symbol"] = symbol
        return d

    def _stub_get_stock_detail(symbol):
        d = dict(stock_detail)
        d["symbol"] = symbol
        return d

    def _stub_screen_stocks(query=None, max_results=10):
        return [
            {"symbol": SAMPLE_SYMBOL, "shortName": "Samsung Electronics",
             "trailingPE": 10.5, "exchange": "KSC"},
            {"symbol": SAMPLE_SYMBOL_2, "shortName": "SK hynix",
             "trailingPE": 18.2, "exchange": "KSC"},
        ][:max_results]

    def _stub_get_price_history(symbol, period="3mo"):
        import pandas as pd
        # 단순 상승 추세 시계열 (원화 기준)
        prices = [70000 + i * 100 for i in range(60)]
        return pd.DataFrame({
            "Open": prices,
            "High": [p + 500 for p in prices],
            "Low": [p - 500 for p in prices],
            "Close": prices,
            "Volume": [10_000_000] * 60,
        })

    def _stub_get_macro_indicators():
        return {"KOSPI": 3200.0, "VIX": 18.5, "USD/KRW": 1400.0}

    monkeypatch.setattr("tools.yahoo_finance.get_stock_info", _stub_get_stock_info)
    monkeypatch.setattr("tools.yahoo_finance.get_stock_detail", _stub_get_stock_detail)
    monkeypatch.setattr("tools.yahoo_finance.screen_stocks", _stub_screen_stocks)
    monkeypatch.setattr("tools.yahoo_finance.get_price_history", _stub_get_price_history)
    monkeypatch.setattr("tools.yahoo_finance.get_macro_indicators", _stub_get_macro_indicators)

    # 4) Grok stub
    def _stub_search_market(query):
        return {
            "summary": f"[mock] {query} 시황: 중립",
            "macro_factors": ["금리 동결", "VIX 18.5", "외국인 순매수"],
            "sentiment": {"score": 0.0, "summary": "neutral"},
        }

    def _stub_search_x_sentiment(symbol, name):
        return {
            "score": 0.3,
            "summary": f"[mock] {symbol} 센티먼트: 강세 우위",
            "positive": ["EPS 성장"],
            "negative": ["높은 PER"],
        }

    monkeypatch.setattr("tools.grok.search_market", _stub_search_market, raising=False)
    monkeypatch.setattr("tools.grok.search_x_sentiment", _stub_search_x_sentiment, raising=False)

    # 5) sample fixtures 를 data/ 에 복사 (agent 가 직접 data/ 를 읽는 경우 대비)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "portfolio.csv").write_text(SAMPLE_PORTFOLIO.read_text())
    (data_dir / "cash_balance.json").write_text(SAMPLE_CASH.read_text())
    monkeypatch.setenv("STOCK_SKILLS_DATA_DIR", str(data_dir))


# ---------------------------------------------------------------------------
# Scenario tests (시나리오 단위의 동작 검증)
# ---------------------------------------------------------------------------


def test_scenario_screener_routing():
    """e2e_001: "좋은 한국 주식 있어?" → screener 로 라우팅되고 기대 툴이 나온다."""
    from src.orchestrator import verify_routing
    r = verify_routing("좋은 한국 주식 있어?")
    assert r.passed
    assert r.agents == ["screener"]
    assert any("screen" in t for t in r.expected_tools)


def test_scenario_screener_yahoo_call_returns_mocked_data():
    """screener 가 호출하는 screen_stocks 가 mock 응답을 반환한다."""
    from tools.yahoo_finance import screen_stocks
    result = screen_stocks(max_results=5)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["symbol"] == SAMPLE_SYMBOL
    assert result[0]["exchange"] in ("KSC", "KOE")


def test_scenario_analyst_routing_and_data():
    """e2e_002: "삼성전자 어때?" → analyst + stock_info 취득."""
    from src.orchestrator import verify_routing
    from tools.yahoo_finance import get_stock_info, get_stock_detail

    r = verify_routing("삼성전자 어때?")
    assert r.passed
    assert r.agents == ["analyst"]

    info = get_stock_info(SAMPLE_SYMBOL)
    detail = get_stock_detail(SAMPLE_SYMBOL)
    assert info["symbol"] == SAMPLE_SYMBOL
    # PER 등 주요 지표가 포함된다 (fixture 경유)
    assert "per" in info or "trailingPE" in info


def test_scenario_health_checker_uses_sample_portfolio():
    """e2e_003: PF 확인 계열에서 sample_portfolio 가 읽힌다."""
    from src.data.portfolio_io import load_portfolio
    positions = load_portfolio(str(SAMPLE_PORTFOLIO))
    assert len(positions) >= 5
    symbols = [p["symbol"] for p in positions]
    assert "AAPL" in symbols  # sample fixture 의 미국 종목
    assert SAMPLE_SYMBOL in symbols  # sample fixture 의 한국 종목
    # 한국 (.KS/.KQ) 또는 미국 (접미사 없음) 종목만 포함. 일본 티커 (.T) 는 없다
    assert all(not s.endswith(".T") for s in symbols)
    # 통화는 KRW / USD 만
    assert all(p.get("cost_currency") in ("KRW", "USD") for p in positions)


def test_scenario_health_checker_sample_cash_balance_is_krw():
    """e2e_003: sample_cash_balance 가 KRW 기준 스키마 (total_krw) 를 따른다."""
    cash = json.loads(SAMPLE_CASH.read_text())
    assert "total_krw" in cash
    assert "KRW" in cash["breakdown"]
    assert "USD" in cash["breakdown"]
    assert "krw_equivalent" in cash["breakdown"]["USD"]


def test_scenario_researcher_grok_returns_mock():
    """e2e_004: researcher 의 grok 호출이 mock 응답을 반환한다."""
    from tools.grok import search_market

    result = search_market("한국 증시 시황")
    assert "[mock]" in result["summary"]
    assert "sentiment" in result


def test_scenario_strategist_chain_routing():
    """e2e_006: "PF 개선하고 싶어" 가 연쇄 (HC→strategist) 로 라우팅된다."""
    from src.orchestrator import verify_routing
    r = verify_routing("PF 개선하고 싶어")
    assert r.passed
    assert "health-checker" in r.agents
    assert "strategist" in r.agents
    # history_check 플래그가 선다 (KIK-740)
    assert r.flags.get("history_check") is True


def test_scenario_sell_decision_with_history_check():
    """e2e_007: "이 종목 팔아야 해?" 에서 history_check + review 가 선다."""
    from src.orchestrator import verify_routing
    r = verify_routing("이 종목 팔아야 해?")
    assert r.passed
    assert r.flags.get("history_check") is True
    assert r.flags.get("review") is True
    # 3 에이전트 연쇄 (risk-assessor → HC → strategist)
    assert len(r.agents) == 3


# ---------------------------------------------------------------------------
# Smoke tests (즉시 PASS, CI 의 sanity check 로 사용 가능)
# ---------------------------------------------------------------------------


def test_no_api_keys_present():
    """API keys 가 삭제되어 있다 (fixture 의 효력 확인)."""
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        assert os.environ.get(k) is None, f"{k} should be removed by fixture"


def test_llm_stub_returns_mock_string():
    """tools.llm.call_llm 이 stub 응답을 반환한다."""
    from tools.llm import call_llm
    result = call_llm("gpt", "gpt-5.5", "test prompt")
    assert "[mock:gpt]" in result
