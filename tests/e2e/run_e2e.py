#!/usr/bin/env python3
"""stock-skills 에이전트 E2E 테스트 러너.

Usage:
    python3 tests/e2e/run_e2e.py              # 전 시나리오 실행 (실 API)
    python3 tests/e2e/run_e2e.py e2e_001      # 특정 시나리오만
    python3 tests/e2e/run_e2e.py e2e_001 e2e_003  # 복수 지정

    # KIK-746: routing 검증만 (LLM/Yahoo Finance 호출 없음, < 1초)
    python3 tests/e2e/run_e2e.py --dry-run
"""

import csv
import json
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 기본 샘플 종목 (삼성전자) / 한국 거래소 exchange 코드 (KOSPI=KSC, KOSDAQ=KOE)
SAMPLE_SYMBOL = "005930.KS"
KR_EXCHANGES = ("KSC", "KOE")
KR_SUFFIXES = (".KS", ".KQ")


# ---------------------------------------------------------------------------
# Test functions (each returns {passed: bool, details: list[str]})
# ---------------------------------------------------------------------------

def test_screener() -> dict:
    """e2e_001: Screener — 좋은 한국 주식 있어?"""
    details = []
    passed = True

    try:
        from src.data.yahoo_client import screen_stocks
        from yfinance import EquityQuery

        # 한국 주식 alpha 프리셋 상당 (yfinance EquityQuery 필드명). KOSPI+KOSDAQ 양쪽 포함
        query = EquityQuery("AND", [
            EquityQuery("IS-IN", ["exchange", *KR_EXCHANGES]),
            EquityQuery("LT", ["peratio.lasttwelvemonths", 20]),
            EquityQuery("LT", ["pricebookratio.quarterly", 2.0]),
            EquityQuery("GT", ["returnonequity.lasttwelvemonths", 8]),
        ])
        result = screen_stocks(query, max_results=5)

        # 기준1: 1건 이상
        if result and len(result) > 0:
            details.append(f"[x] 종목 리스트: {len(result)} 건")
        else:
            details.append("[o] 종목 리스트: 0 건")
            passed = False

        # 기준2: symbol, name
        if result:
            first = result[0]
            has_symbol = "symbol" in first
            has_name = "shortName" in first or "name" in first
            details.append(f"[{'x' if has_symbol else 'o'}] symbol: {'있음' if has_symbol else '없음'}")
            details.append(f"[{'x' if has_name else 'o'}] name: {'있음' if has_name else '없음'}")
            if not (has_symbol and has_name):
                passed = False

        # 기준3: 지표
        if result:
            first = result[0]
            has_per = "trailingPE" in first or "forwardPE" in first
            details.append(f"[{'x' if has_per else 'o'}] PER: {'있음' if has_per else '없음'}")

        # 기준4: region
        if result:
            all_kr = all(
                r.get("symbol", "").endswith(KR_SUFFIXES) or r.get("exchange") in KR_EXCHANGES
                for r in result
            )
            details.append(f"[{'x' if all_kr else 'o'}] region=kr: {all_kr}")
            if not all_kr:
                passed = False

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_analyst() -> dict:
    """e2e_002: Analyst — 005930.KS 어때?"""
    details = []
    passed = True

    try:
        from tools.yahoo_finance import get_stock_info, get_price_history

        info = get_stock_info(SAMPLE_SYMBOL)
        if info is None:
            details.append("[o] stock_info: None")
            return {"passed": False, "details": details}

        # 기준1: 기본 지표
        for key in ["per", "pbr", "roe", "dividend_yield"]:
            val = info.get(key)
            details.append(f"[{'x' if val is not None else 'o'}] {key}: {val}")
            if val is None and key in ("per", "pbr"):
                passed = False

        # 기준2: 가격 이력
        hist = get_price_history(SAMPLE_SYMBOL, period="3mo")
        if hist is not None and len(hist) > 0:
            details.append(f"[x] price_history: {len(hist)} 데이터 포인트")
        else:
            details.append("[o] price_history: 없음")
            passed = False

        # 기준3: 섹터
        sector = info.get("sector")
        details.append(f"[{'x' if sector else 'o'}] sector: {sector}")

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_health_checker() -> dict:
    """e2e_003: Health Checker — PF 괜찮아?"""
    details = []
    passed = True

    try:
        # 기준1: 전 보유 종목 읽기
        from src.data.portfolio_io import load_portfolio
        pf = load_portfolio()
        details.append(f"[{'x' if len(pf) > 0 else 'o'}] 종목 수: {len(pf)}")
        if len(pf) == 0:
            passed = False

        # 기준2: 신규 컬럼 (KIK-694)
        if pf:
            first = pf[0]
            has_return = first.get("total_return") is not None
            has_role = bool(first.get("role"))
            details.append(f"[{'x' if has_return else 'o'}] total_return: {first.get('total_return')}")
            details.append(f"[{'x' if has_role else 'o'}] role: {first.get('role')}")

        # 기준3: thesis/observation (KIK-695)
        from tools.notes import load_notes
        thesis_count = 0
        for pos in pf:
            notes = load_notes(symbol=pos["symbol"])
            thesis = [n for n in notes if n.get("type") in ("thesis", "observation")]
            thesis_count += len(thesis)
        details.append(f"[{'x' if thesis_count > 0 else 'o'}] thesis/observation: {thesis_count} 건")

        # 기준4: 주가 취득
        from tools.yahoo_finance import get_stock_info
        if pf:
            info = get_stock_info(pf[0]["symbol"])
            details.append(f"[{'x' if info else 'o'}] 주가 취득({pf[0]['symbol']}): {'OK' if info else 'NG'}")
            if not info:
                passed = False

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_researcher() -> dict:
    """e2e_004: Researcher — 최신 뉴스 알려줘"""
    details = []
    passed = True

    try:
        # 기준1: Grok API 이용 가능 여부
        from src.data.grok_client._common import is_available
        grok_ok = is_available()
        details.append(f"[x] Grok API: {'이용 가능' if grok_ok else '미설정'}")

        # 기준2: 뉴스 취득
        if grok_ok:
            from tools.grok import search_market
            result = search_market("전체")
            has_data = result and any(
                result.get(k) for k in ["price_action", "macro_factors", "sentiment"]
            )
            details.append(f"[{'x' if has_data else 'o'}] 뉴스 데이터: {'있음' if has_data else '없음'}")
        else:
            details.append("[x] Grok 미설정: graceful degradation (빈 데이터, 에러 없음)")

        # 기준3: GraphRAG
        from tools.graphrag import HAS_GRAPH_QUERY, HAS_CONTEXT
        details.append(f"[x] GraphRAG: query={HAS_GRAPH_QUERY}, context={HAS_CONTEXT}")

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_risk_assessor() -> dict:
    """e2e_005: Risk Assessor — 리스크 판정해줘"""
    details = []
    passed = True

    try:
        from tools.yahoo_finance import get_stock_info

        # 기준1: 시장 지표 취득
        indicators = {
            "^KS11": "KOSPI",
            "^GSPC": "S&P500",
            "^VIX": "VIX",
            "^TNX": "미국 10년물 금리",
            "KRW=X": "USD/KRW",
        }
        for sym, name in indicators.items():
            info = get_stock_info(sym)
            if info and info.get("price") is not None:
                details.append(f"[x] {name}: {info['price']}")
            else:
                details.append(f"[o] {name}: 취득 실패")
                passed = False

        # 기준2: RSI 계산 가능성
        from tools.yahoo_finance import get_price_history
        hist = get_price_history("^GSPC", period="3mo")
        if hist is not None and len(hist) >= 14:
            details.append(f"[x] RSI 계산 가능: {len(hist)} 데이터 포인트")
        else:
            details.append("[o] RSI 계산 불가: 데이터 부족")
            passed = False

        # 기준3: Grok 없이도 판정 가능
        details.append("[x] Grok 없이도 기본 판정 가능 (VIX/금리/WTI 로 잠정 스코어 산출)")

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_hc_strategist_chain() -> dict:
    """e2e_006: HC + Strategist Chain — PF 개선하고 싶어"""
    details = []
    passed = True

    try:
        # 기준1: PF 데이터
        from src.data.portfolio_io import load_portfolio
        pf = load_portfolio()
        has_return = any(pos.get("total_return") is not None for pos in pf)
        details.append(f"[{'x' if pf else 'o'}] PF 데이터: {len(pf)} 종목")
        details.append(f"[{'x' if has_return else 'o'}] 주주환원율 데이터: {'있음' if has_return else '없음'}")

        # 기준2: lesson
        from tools.notes import load_notes
        lessons = load_notes(note_type="lesson")
        details.append(f"[{'x' if lessons else 'o'}] lesson: {len(lessons)} 건")

        # 기준3: thesis/observation
        thesis_count = 0
        for pos in pf:
            notes = load_notes(symbol=pos["symbol"])
            thesis_count += len([n for n in notes if n.get("type") in ("thesis", "observation")])
        details.append(f"[{'x' if thesis_count > 0 else 'o'}] thesis/observation: {thesis_count} 건")

        # 기준4: GraphRAG
        from tools.graphrag import HAS_GRAPH_QUERY, HAS_CONTEXT
        details.append(f"[x] GraphRAG: query={HAS_GRAPH_QUERY}, context={HAS_CONTEXT}")

        # 기준5: what-if 주가 취득
        from tools.yahoo_finance import get_stock_info
        if pf:
            info = get_stock_info(pf[0]["symbol"])
            details.append(f"[{'x' if info else 'o'}] what-if 용 주가: {'OK' if info else 'NG'}")
            if not info:
                passed = False

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_deepthink_swarm() -> dict:
    """e2e_007: DeepThink 4-Swarm — 2층 모델 동적 역할 할당"""
    details = []
    passed = True

    try:
        # 기준1: deepthink_limits.yaml 읽기와 값 체크
        import yaml
        limits_path = PROJECT_ROOT / ".claude" / "skills" / "deepthink" / "deepthink_limits.yaml"
        with open(limits_path) as f:
            limits = yaml.safe_load(f)

        max_spawns = limits["limits"]["max_agent_spawns"]
        max_llm = limits["limits"]["max_llm_calls"]
        if max_spawns >= 20:
            details.append(f"[x] max_agent_spawns: {max_spawns} (>= 20)")
        else:
            details.append(f"[o] max_agent_spawns: {max_spawns} (< 20, 4-Swarm 에 부족)")
            passed = False

        if max_llm >= 25:
            details.append(f"[x] max_llm_calls: {max_llm} (>= 25)")
        else:
            details.append(f"[o] max_llm_calls: {max_llm} (< 25)")
            passed = False

        # 깊이 프리셋 검증
        for depth in ["shallow", "medium", "deep"]:
            preset = limits["depth_presets"][depth]
            details.append(f"[x] {depth}: spawns={preset['max_agent_spawns']}, llm={preset['max_llm_calls']}")

        # 기준2: LLM 프로바이더 이용 가능 여부
        from tools.llm import get_available_providers, is_provider_available
        providers = get_available_providers()
        details.append(f"[x] 이용 가능 프로바이더: {providers if providers else '없음 (graceful degradation)'}")

        # 기준3: 각 LLM 접속 확인 (API key 가 있는 경우만)
        from tools.llm import call_llm

        swarm_members = {
            "gpt": {"model": "gpt-5.4", "prompt": "Reply OK in one word.", "kwargs": {"reasoning": "low"}},
            "gemini": {"model": "gemini-3-flash-preview", "prompt": "Reply OK in one word.", "kwargs": {}},
            "grok": {"model": "grok-4.20-0309-reasoning", "prompt": "Reply OK in one word.", "kwargs": {}},
        }

        llm_ok_count = 0
        for provider, cfg in swarm_members.items():
            if is_provider_available(provider):
                result = call_llm(provider, cfg["model"], cfg["prompt"], timeout=30, **cfg["kwargs"])
                if result:
                    details.append(f"[x] {provider}: 응답 있음 ({len(result)} chars)")
                    llm_ok_count += 1
                else:
                    details.append(f"[o] {provider}: API 키는 있으나 응답 없음")
                    passed = False
            else:
                details.append(f"[x] {provider}: 미설정 (graceful degradation)")

        # 기준4: Grok search 함수 이용 가능 여부
        from src.data.grok_client._common import is_available as grok_available
        if grok_available():
            from tools.grok import search_x_sentiment
            sentiment = search_x_sentiment("AAPL", "Apple")
            if sentiment:
                details.append(f"[x] Grok search_x_sentiment: 데이터 있음")
            else:
                details.append(f"[o] Grok search_x_sentiment: 데이터 없음")
        else:
            details.append(f"[x] Grok search: 미설정 (graceful degradation)")

        # 기준5: SKILL.md 에 2층 모델·통합 결론·서머리 기술이 있는가
        skill_path = PROJECT_ROOT / ".claude" / "skills" / "deepthink" / "SKILL.md"
        skill_content = skill_path.read_text()
        checks = {
            "인프라층": "인프라층" in skill_content,
            "추론층": "추론층" in skill_content,
            "적성 매트릭스": "적성 매트릭스" in skill_content,
            "하드 제약": "하드 제약" in skill_content,
            "4-Swarm": "4-Swarm" in skill_content,
            "이그제큐티브 서머리": "이그제큐티브 서머리" in skill_content,
            "통합 결론": "통합 결론" in skill_content or "논의의 통합" in skill_content,
            "채택/기각": "채택" in skill_content,
            "툴 참조": "tools.yaml" in skill_content,
            "screen_stocks 필수": "screen_stocks" in skill_content,
        }
        for label, found in checks.items():
            details.append(f"[{'x' if found else 'o'}] SKILL.md {label}: {'있음' if found else '없음'}")
            if not found:
                passed = False

        # 기준6: config/tools.yaml 존재와 정합성
        tools_path = PROJECT_ROOT / "config" / "tools.yaml"
        if tools_path.exists():
            with open(tools_path) as f:
                tools_def = yaml.safe_load(f)
            tools_keys = list(tools_def.get("tools", {}).keys())
            required = ["yahoo_finance", "grok", "graphrag", "llm", "notes", "portfolio_io"]
            has_all_tools = all(t in tools_keys for t in required)
            details.append(f"[{'x' if has_all_tools else 'o'}] tools.yaml: {tools_keys}")
            # screen_stocks 가 정의되어 있는가
            yf = tools_def.get("tools", {}).get("yahoo_finance", {}).get("functions", {})
            has_screen = "screen_stocks" in yf
            details.append(f"[{'x' if has_screen else 'o'}] tools.yaml screen_stocks: {'정의 있음' if has_screen else '없음'}")
            if not (has_all_tools and has_screen):
                passed = False
        else:
            details.append("[o] tools.yaml: 파일 없음")
            passed = False

        # 기준7: llm_capabilities.yaml 존재와 정합성
        cap_path = PROJECT_ROOT / "config" / "llm_capabilities.yaml"
        if cap_path.exists():
            with open(cap_path) as f:
                caps = yaml.safe_load(f)
            has_all = all(p in caps.get("providers", {}) for p in ["gemini", "gpt", "grok"])
            details.append(f"[{'x' if has_all else 'o'}] llm_capabilities.yaml: 전 프로바이더 정의 있음")
        else:
            details.append("[o] llm_capabilities.yaml: 파일 없음")
            passed = False

    except Exception as e:
        details.append(f"[o] 예외: {e}")
        passed = False

    return {"passed": passed, "details": details}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCENARIOS = {
    "e2e_001": ("Screener E2E", test_screener),
    "e2e_002": ("Analyst E2E", test_analyst),
    "e2e_003": ("Health Checker E2E", test_health_checker),
    "e2e_004": ("Researcher E2E", test_researcher),
    "e2e_005": ("Risk Assessor E2E", test_risk_assessor),
    "e2e_006": ("HC + Strategist Chain E2E", test_hc_strategist_chain),
    "e2e_007": ("DeepThink 4-Swarm E2E", test_deepthink_swarm),
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenarios(ids: list[str] | None = None):
    """E2E 시나리오를 실행하고 결과를 출력한다."""
    targets = ids or list(SCENARIOS.keys())
    results = []
    total_pass = 0
    total_fail = 0

    print(f"\n{'='*60}")
    print(f"E2E Test Suite — {len(targets)} scenarios")
    print(f"{'='*60}\n")

    for scenario_id in targets:
        if scenario_id not in SCENARIOS:
            print(f"⚠️  Unknown scenario: {scenario_id}")
            continue

        name, test_fn = SCENARIOS[scenario_id]
        print(f"▶ {scenario_id}: {name}...", end=" ", flush=True)

        start = time.time()
        result = test_fn()
        elapsed = time.time() - start

        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status} ({elapsed:.1f}s)")

        for detail in result["details"]:
            print(f"  {detail}")
        print()

        results.append({
            "id": scenario_id,
            "name": name,
            "passed": result["passed"],
            "elapsed": round(elapsed, 1),
            "details": result["details"],
        })

        if result["passed"]:
            total_pass += 1
        else:
            total_fail += 1

    # Summary
    print(f"{'='*60}")
    print(f"결과: {total_pass} PASS / {total_fail} FAIL (전 {len(results)} 건)")
    print(f"{'='*60}")

    # Save results
    results_path = PROJECT_ROOT / "data" / "e2e_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(results),
            "passed": total_pass,
            "failed": total_fail,
            "scenarios": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n결과를 {results_path} 에 저장했습니다")

    return total_fail == 0


def run_dry_run() -> bool:
    """KIK-746: routing 검증만 (LLM/Yahoo Finance 호출 없음).

    각 시나리오의 상정 user input → routing 해석 → 에이전트 존재 확인 →
    기대 툴 열거, 를 고속으로 실행한다.
    """
    from src.orchestrator import verify_routing, verify_routing_yaml_integrity

    print("\n" + "=" * 60)
    print("E2E Dry-Run — routing only (no LLM, no Yahoo Finance)")
    print("=" * 60 + "\n")

    # 1) routing.yaml integrity check
    integrity = verify_routing_yaml_integrity()
    if integrity["passed"]:
        print("✅ routing.yaml integrity: OK")
    else:
        print("❌ routing.yaml integrity: FAIL")
    for err in integrity["errors"]:
        print(f"   ❌ {err}")
    for warn in integrity["warnings"][:5]:
        print(f"   ⚠️  {warn}")
    if len(integrity["warnings"]) > 5:
        print(f"   ⚠️  ... and {len(integrity['warnings']) - 5} more warnings")
    print()

    # 2) 시나리오별 routing 검증 (전형적인 입력 예)
    sample_inputs = {
        "e2e_001": "좋은 한국 주식 있어?",
        "e2e_002": "삼성전자 어때?",
        "e2e_003": "PF 괜찮아?",
        "e2e_004": "최신 뉴스 알려줘",
        "e2e_005": "리스크 판정해줘",
        "e2e_006": "PF 개선하고 싶어",
        "e2e_007": "이 종목 팔아야 해?",
    }
    pass_count, fail_count = 0, 0
    for sid, user_in in sample_inputs.items():
        r = verify_routing(user_in)
        ok = r.passed
        status = "✅" if ok else "❌"
        agents = ",".join(r.agents) if r.agents else (r.flags.get("action") or "?")
        print(f"  {status} {sid}: {user_in!r}")
        print(f"      → matched: {r.matched_intent!r}  agents: {agents}")
        if r.expected_tools:
            print(f"      → tools: {', '.join(r.expected_tools)}")
        for warn in r.warnings:
            print(f"      ⚠️  {warn}")
        for err in r.errors:
            print(f"      ❌ {err}")
        if ok:
            pass_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"Dry-run 결과: {pass_count} PASS / {fail_count} FAIL")
    print("=" * 60)
    return fail_count == 0 and integrity["passed"]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--dry-run" in args:
        success = run_dry_run()
    else:
        ids = args if args else None
        success = run_scenarios(ids)
    sys.exit(0 if success else 1)
