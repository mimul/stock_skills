# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Design Philosophy

**이 시스템은 「자연어 퍼스트」의 Agentic AI Pattern 으로 설계되어 있다.**

사용자는 명령어나 파라미터를 외울 필요가 없다. 한국어로 의도를 전달하기만 하면 오케스트레이터가 적절한 에이전트를 자율적으로 선택·기동한다.

- 「좋은 한국 주식 있어?」→ Screener 가 자율적으로 region/preset 을 정해 스크리닝
- 「삼성전자 어때?」→ Analyst 가 밸류에이션·테크니컬 분석을 실행
- 「PF 괜찮아?」→ Health Checker 가 사실·수치를 내고, Strategist 가 추천
- 「최신 뉴스 알려줘」→ Researcher 가 Grok API 로 뉴스·센티먼트를 수집

에이전트는 툴(tools/)을 사용해 데이터를 가져오고, 스스로 판단·정형화해 출력한다.

## Project Overview

투자 어시스턴트 시스템. Yahoo Finance API（yfinance）, Grok API（xAI）, Neo4j（GraphRAG）를 통합해 자연어로 종목 탐색·분석·포트폴리오 관리·리스크 평가를 수행한다. Claude Code 의 Agentic AI Pattern 으로 동작한다. 기준 시장은 한국(KOSPI `.KS` / KOSDAQ `.KQ`), 보조 시장은 미국, 기준 통화는 KRW(외화는 USD 만 지원), 매매 단위는 한국·미국 모두 1주다.

## Commands

```bash
# 유닛 테스트（API key/네트워크 불필요, 약 1,400 테스트）
python3 -m pytest tests/ -q

# Dry-run（routing.yaml + agent 정의 정합성 검증, < 1초）KIK-746
python3 tests/e2e/run_e2e.py --dry-run

# 모의 E2E（pytest fixture 로 tools 층 stub 화, < 1초）KIK-747
python3 -m pytest tests/e2e/test_mocked.py -q

# 실제 API E2E 테스트（실제 API 로 에이전트 동작 검증, API key 필요）
python3 tests/e2e/run_e2e.py

# 개발용 worktree 셋업（KIK-745, 개인 PF 를 흘리지 않음）
bash scripts/setup_worktree.sh KIK-NNN [short-desc]

# 의존성 설치
pip install -r requirements.txt
```

에이전트가 자율적으로 툴을 호출하므로 사용자가 스크립트를 직접 실행할 필요는 없다.

## Output & Visibility v1（KIK-729）

모든 에이전트 출력은 4레이어 구성으로 생성된다. 자세한 내용은 `.claude/skills/stock-skills/SKILL.md` 의 「Output & Visibility v1」 섹션 참조.

- **Layer 1**: 헤더（실행 전·항상 ON）`🎯 [<agent or chain>] <task>`
- **Layer 2**: 진행（체인 시에만）`✅ <agent> 완료 (X.Xs) — <요약>`
- **Layer 3**: 본문（Pattern A/B/C 로 전환）
  - A: 미니멀（1-3줄로 끝나는 사실 조회）
  - B: 표준（단일 에이전트·4섹션 고정）
  - C: 체인（연쇄 ≥2 / routine）
- **Layer 4**: 푸터（순서 고정）`📊 실행 → 💾 저장 → 🔍 Reviewer? → ➡ 다음`

Reviewer 는 3분류로 기동: 🔒 자동（매매 확정/conviction 위반/주간 routine） / 🔍 애드혹（[y/skip] 프롬프트） / ⏭ 스킵.

## Architecture

자세한 내용은 [docs/architecture.md](docs/architecture.md), [docs/neo4j-schema.md](docs/neo4j-schema.md) 참조.

```
Orchestrator (.claude/skills/stock-skills/)
  SKILL.md          — 라우팅·자율 제어
  routing.yaml      — 에이전트 선택 few-shot
  orchestration.yaml — 재시도·에스컬레이션

Agents (.claude/agents/)
  screener/     — 종목 찾기·스크리닝
  analyst/      — 종목 분석·밸류에이션 평가
  researcher/   — 뉴스·센티먼트·업계 동향
  health-checker/ — PF 의 사실·수치（판단하지 않음）
  strategist/   — 투자 판단·추천
  risk-assessor/ — 시장 리스크 판정（risk-on/neutral/risk-off）
  reviewer/     — 품질·모순·리스크 체크（멀티 LLM）

Tools (tools/)
  yahoo_finance.py — 주가·펀더멘털（src/data/yahoo_client/ 의 파사드）
  graphrag.py      — Neo4j 지식 그래프（src/data/graph_store/ + graph_query/ 의 파사드）
  grok.py          — Grok API 검색（src/data/grok_client/ 의 파사드）
  llm.py           — 멀티 LLM 호출（Gemini/GPT/Grok）
  portfolio_io.py  — PF CSV 읽기/쓰기（src/data/portfolio_io 의 파사드）
  notes.py         — 투자 메모 읽기/쓰기（src/data/note_manager 의 파사드）
  watchlist.py     — 워치리스트 읽기/쓰기（JSON 직접 I/O）
  scoring.py       — 3축 품질 스코어링（src/data/scoring.py 의 파사드）

Data (src/data/)
  yahoo_client/  — yfinance 래퍼（24h JSON 캐시）. kr_fundamentals.py 는 분기 재무제표 기반 TTM PER/PBR 계산
  kr_valuation/  — 한국 종목 PER/PBR/EPS/BPS 보강（공급자: pykrx → yfinance-ttm）
  grok_client/   — Grok API (xAI) 래퍼
  graph_store/   — Neo4j 쓰기（dual-write）
  graph_query/   — Neo4j 읽기
  context/       — 자동 컨텍스트 주입
  history/       — 실행 이력 스토어
  note_manager   — 투자 메모 관리
  common.py      — 공통 유틸리티（is_etf, safe_float 등）
  ticker_utils.py — 티커 추론（통화/지역 매핑: KRW/USD, kr/us）
  portfolio_io.py — PF CSV 읽기/쓰기
  scoring.py     — 3축 품질 스코어링（환원성·성장성·지속성）

Orchestrator (src/orchestrator/) — KIK-746
  dry_run.py     — routing.yaml + agent 정의 정합성 검증（API 호출 없음）
                   verify_routing(user_input), verify_routing_yaml_integrity()

Scripts (scripts/) — KIK-745
  setup_worktree.sh — worktree 생성 + sample fixture 복사 일괄화（개인 PF 를 흘리지 않음）

Config: .claude/agents/screener/examples.yaml (regions(kr/us), themes, presets, few-shot)
Config: config/scoring.yaml (스코어링 가중치·임계값·섹터별 설정)
Config: config/allocation.yaml (PF 목표 배분·집중도 제약·괴리 판정)
Config: config/etf_universe.yaml (ETF 정석 리스트 — 한국/미국 섹터·채권·원자재·지역)
Config: config/llm_routing.yaml (LLM 선택·모델 라우팅·비용 정의)
Rules:  .claude/rules/ (development, workflow, testing)
Docs:   docs/ (architecture, neo4j-schema, data-models)
Tests:  tests/ (unit 약 1,400건), tests/e2e/ (E2E)
        - run_e2e.py: 실제 API 시나리오 실행
        - run_e2e.py --dry-run: routing 검증만（< 1초）KIK-746
        - test_mocked.py: 모의 E2E（pytest fixture 로 tools stub）KIK-747
Fixtures: tests/fixtures/sample_portfolio.csv / sample_cash_balance.json
          (KIK-745, 범용 테스트 종목, worktree 통합 시험에서 개인 PF 대체)
```

## Post-Implementation Rule

**기능 구현 후에는 반드시 아래를 확인·갱신할 것.**

- 에이전트 정의: 해당 `agent.md` + `examples.yaml`
- 라우팅: `routing.yaml` 의 triggers/examples
- 문서: `CLAUDE.md`, `README.md`, `docs/architecture.md`
- 테스트: `python3 -m pytest tests/ -q` 로 전체 PASS 확인
