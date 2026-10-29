# stock-skills

투자 어시스턴트 시스템. Agentic AI Pattern 으로 설계. 자연어로 말을 걸기만 하면 종목 탐색·분석·포트폴리오 관리·리스크 평가가 자동으로 실행된다. 기준 시장은 한국(KOSPI/KOSDAQ), 보조 시장은 미국이며 기준 통화는 KRW 다.

## 시스템 요구사항

- **[Claude Code](https://claude.ai/code)** — 본 시스템의 런타임. SKILL.md 를 오케스트레이터로 읽어 들여 에이전트를 자율적으로 기동·제어한다. Claude Code 없이는 동작하지 않는다
- **Python 3.10+** — 툴(tools/)의 실행 환경
- **Anthropic 구독** — Claude Code 이용에 필요

## 설치

```bash
pip install -r requirements.txt
```

의존성: yfinance, pyyaml, numpy, pandas, requests, python-dotenv

### 환경 변수

```bash
# Grok API（X 센티먼트 분석, 선택）
export XAI_API_KEY=xai-xxxxxxxxxxxxx

# Gemini API（멀티 LLM 리뷰, 선택）
export GEMINI_API_KEY=AIzaSy...

# OpenAI API（멀티 LLM 리뷰, 선택）
export OPENAI_API_KEY=sk-proj-...

# Neo4j（GraphRAG, 선택）
export NEO4J_URI=bolt://localhost:7688
export NEO4J_MODE=full  # off/summary/full
export NEO4J_DEBUG=1    # 접속 실패 시 진단을 최초 1회만 stderr 에 출력（기본: 무음）

# KRX 정보데이터시스템（한국 종목 PER/PBR 전종목 스냅샷, 선택）
# data.krx.co.kr 무료 계정. pip install pykrx 도 필요. 미설정이면 yfinance 분기 재무제표로 TTM PER/PBR 을 계산한다
export KRX_ID=...
export KRX_PW=...
```

모두 선택 사항. 설정하지 않아도 기본값으로 동작한다.

## 사용법

자연어로 말을 걸기만 하면 된다:

```
「좋은 한국 주식 있어?」      → Screener 가 자율적으로 스크리닝
「삼성전자 어때?」            → Analyst 가 밸류에이션 분석
「최신 뉴스 알려줘」          → Researcher 가 Grok API 로 뉴스 수집
「PF 괜찮아?」               → Health Checker 가 수치를 내고, Strategist 가 추천
「폭락하면 어떻게 돼?」        → Health Checker 가 스트레스 테스트 실행
「메모해 둬」                → 투자 메모를 직접 저장
```

### 출력 포맷（Output & Visibility v1）

모든 응답은 4레이어 구성으로 표시된다（KIK-729）.

```
🎯 [<agent or chain>] <task summary>        ← Layer 1 헤더（항상 표시）
✅ <agent> 완료 (X.Xs) — <1줄 요약>          ← Layer 2 진행（체인 시에만）

[Layer 3 본문: Pattern A/B/C 로 전환]
- Pattern A: 미니멀（VIX/TODO/가격 등 즉답）
- Pattern B: 표준 4섹션（단일 에이전트 분석）
- Pattern C: 체인（복수 에이전트 연쇄·routine）

📊 실행: A → B → C                          ← Layer 4 푸터（순서 고정）
💾 저장: data/<path>
🔍 Reviewer 로 체크할까? [y/skip]
➡ 다음: <다음 액션 제안>
```

Reviewer 는 **3분류로 기동 제어**:
- 🔒 **자동**: 매매 확정 직전 / conviction 위반 감지 / 주간 routine
- 🔍 **애드혹**: 그 외 strategist/screener 등 → 말미에 [y/skip] 프롬프트 → 다음 턴에 `y` 입력으로 기동
- ⏭ **스킵**: HC/researcher/analyst/risk-assessor 단독

## 아키텍처

```
Orchestrator (.claude/skills/stock-skills/)
  ├─ SKILL.md          — 라우팅·자율 제어
  ├─ routing.yaml      — 에이전트 선택 few-shot
  └─ orchestration.yaml — 재시도·에스컬레이션

Agents (.claude/agents/) — 7종
  ├─ screener/       — 종목 찾기（region/preset/theme 을 자율 결정）
  ├─ analyst/        — 밸류에이션·저평가 판정·ETF 평가
  ├─ researcher/     — 뉴스·센티먼트·업계·시황
  ├─ health-checker/ — PF 의 사실·수치（판단하지 않음）
  ├─ strategist/     — 투자 판단·추천（다른 에이전트 결과를 통합）
  ├─ risk-assessor/  — 시장 리스크 판정（risk-on/neutral/risk-off）
  └─ reviewer/       — 품질·리스크 체크（GPT+Gemini+Claude 병렬 리뷰）

Tools (tools/)
  ├─ yahoo_finance.py — 주가·펀더멘털
  ├─ graphrag.py      — Neo4j 지식 그래프
  ├─ grok.py          — Grok API（X/Web 검색）
  └─ llm.py           — 멀티 LLM（Gemini/GPT/Grok）

Data (src/data/) — yahoo_client, grok_client, graph_store, graph_query, common, ticker_utils, portfolio_io
```

자세한 내용은 [docs/architecture.md](docs/architecture.md) 참조.

## Neo4j 지식 그래프（옵션）

에이전트 실행 이력을 Neo4j 에 축적해 과거 분석·매매·리서치를 횡단 검색할 수 있다.

```bash
docker compose up -d
```

**신규 사용은 data/ 로컬 스토리지만으로 완결된다. Neo4j 는 옵션 기능이다.** 이미 Neo4j 를 운용 중이라면 그대로 계속 사용할 수 있다（graceful degradation 완전 대응）. Neo4j 미접속 시에는 `data/notes/`·`data/portfolio.csv`·`data/screening_results/` 등에서 자동 컨텍스트 주입이 동작한다（KIK-719）. 미접속 시 경고는 출력되지 않는다. 진단이 필요하면 `NEO4J_DEBUG=1`（KIK-749）.

## 테스트

```bash
# 유닛 테스트（API key/네트워크 불필요, autouse fixture 로 외부 I/O 를 완전 모킹）
python3 -m pytest tests/ -q           # 약 1,400 테스트 (~55초)

# Dry-run（routing.yaml + agent 정의 정합성 검증, < 1초, API key 불필요）KIK-746
python3 tests/e2e/run_e2e.py --dry-run

# 모의 E2E（pytest fixture 로 tools 층 stub 화, < 1초, API key 불필요）KIK-747
python3 -m pytest tests/e2e/test_mocked.py -q

# 실제 API E2E 테스트（Yahoo Finance / LLM 실제 호출, API key 필요）
python3 tests/e2e/run_e2e.py          # 전체 시나리오 실행 (~25초)
python3 tests/e2e/run_e2e.py e2e_001  # 특정 시나리오만
```

### Worktree 셋업（KIK-745）

개발용 worktree 는 `scripts/setup_worktree.sh` 로 개인 PF 를 쓰지 않고 즉시 셋업:

```bash
bash scripts/setup_worktree.sh KIK-NNN feature-name
# → ~/stock-skills-kikNNN 에 전개, tests/fixtures/sample_portfolio.csv 를
#    data/ 에 복사（범용 테스트 종목, 개인 PF 는 흘리지 않음）
```

### E2E 테스트 시나리오

| ID | 에이전트 | 입력 예 | 검증 내용 |
|:---|:---|:---|:---|
| e2e_001 | Screener | 좋은 한국 주식 있어? | EquityQuery, 종목 리스트, region |
| e2e_002 | Analyst | 005930.KS 어때? | PER/PBR/ROE, 가격 이력 |
| e2e_003 | Health Checker | PF 괜찮아? | 보유 종목 전체, thesis/observation, 환원율 |
| e2e_004 | Researcher | 최신 뉴스 | Grok API, 센티먼트, GraphRAG |
| e2e_005 | Risk Assessor | 리스크 판정해 줘 | VIX/금리/WTI, RSI 계산 |
| e2e_006 | HC + Strategist | PF 개선하고 싶어 | lesson, thesis, what-if |

## v1 에서 이전

v1（[stock_skills](https://github.com/okikusan-public/stock_skills)）에서 이전할 수 있다.

### 데이터 호환성

v1 에서 축적한 아래 데이터는 그대로 v2 에서 사용할 수 있다:

| 데이터 | v1 위치 | v2 위치 | 호환성 |
|:---|:---|:---|:---|
| 투자 메모·lesson | `data/notes/*.json` | `data/notes/*.json` | 완전 호환 |
| 스크리닝 이력 | `data/history/screen/*.json` | `data/history/screen/*.json` | 완전 호환 |
| 매매 기록 | `data/history/trade/*.json` | `data/history/trade/*.json` | 완전 호환 |
| 리포트 이력 | `data/history/report/*.json` | `data/history/report/*.json` | 완전 호환 |
| 리서치 이력 | `data/history/research/*.json` | `data/history/research/*.json` | 완전 호환 |
| 헬스체크 이력 | `data/history/health/*.json` | `data/history/health/*.json` | 완전 호환 |
| 포트폴리오 | `data/portfolio.csv` | `data/portfolio.csv` | 완전 호환 |
| 워치리스트 | `data/watchlists/*.json` | `data/watchlists/*.json` | 완전 호환 |
| Neo4j（GraphRAG） | 그대로 접속 | 그대로 접속 | 완전 호환 |

### 이전 절차

```bash
# 1. v2 클론
git clone https://github.com/okikusan-public/stock_skills_2.git
cd stock_skills_2

# 2. v1 의 data/ 디렉터리 복사
cp -r /path/to/stock_skills/data/ ./data/

# 3. 의존성 설치
pip install -r requirements.txt

# 4. （선택）GraphRAG 와 동기화
# v2 에서 「sync 해 줘」라고 말하면 data/ → Neo4j 동기화가 실행된다
```

v1 의 `scripts/`, `src/output/`, 구 `SKILL.md` 군은 v2 에서 필요 없다. `data/` 만 복사하면 이전이 완료된다.

## 면책 조항

본 소프트웨어는 투자 판단의 참고 정보를 제공하는 것이며, **투자 성과를 보증하지 않는다**. 본 소프트웨어의 출력에 근거한 투자 판단은 모두 이용자 본인의 책임으로 행해야 한다. 개발자는 본 소프트웨어 이용으로 발생한 어떠한 손해에 대해서도 책임을 지지 않는다.

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE) 참조.
