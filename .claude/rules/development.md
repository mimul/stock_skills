# 개발 규칙

## 언어·의존성

- Python 3.10+
- 주요 의존성: yfinance, pyyaml, numpy, pandas, pytest, requests, python-dotenv
- Grok API 이용 시 `XAI_API_KEY` 환경 변수 설정（미설정이어도 동작한다）
- Gemini API 이용 시 `GEMINI_API_KEY` 환경 변수 설정（미설정이어도 동작한다）
- OpenAI API 이용 시 `OPENAI_API_KEY` 환경 변수 설정（미설정이어도 동작한다）
- Neo4j 쓰기 깊이는 `NEO4J_MODE` 환경 변수로 제어: `off`/`summary`/`full`（기본: 접속 가능하면 `full`）
- Neo4j 접속 실패는 기본적으로 무음. 진단이 필요하면 `NEO4J_DEBUG=1`（또는 `true`/`yes`）로 최초 1회만 stderr 에 짧은 줄이 출력된다（KIK-749）
- TEI 벡터 검색은 `TEI_URL` 환경 변수로 제어（기본: `http://localhost:8081`）. 미기동 시 벡터 검색 스킵
- Linear 연동은 `LINEAR_ENABLED=on` 으로 활성화（기본: off）
- 한국 종목 PER/PBR 보강(`src/data/kr_valuation/`)은 `KRX_ID` / `KRX_PW` 환경 변수 + `pip install pykrx` 가 있으면 KRX 스냅샷(pykrx)을, 없으면 yfinance 분기 재무제표 기반 TTM 계산을 쓴다（둘 다 미설정이어도 동작한다）

## 시장·통화 전제

- 기준 시장: 한국 KOSPI（`.KS`, exchange `KSC`）/ KOSDAQ（`.KQ`, exchange `KOE`）. 보조 시장: 미국（접미사 없음）
- 지역 코드는 `kr`, `us` 두 가지만. 기준 통화는 `KRW`, 외화는 `USD` 만 지원
- 한국 종목코드는 6자리 숫자 + 접미사（예: `005930.KS`, `247540.KQ`）. 심볼 정규식은 `\d{6}\.K[SQ]` 를 통째로 매칭한다（`\d{4}` 패턴은 앞자리를 잘라내므로 금지）
- 매매 단위는 한국·미국 모두 1주. `assert_lot_size` / `get_lot_size` 는 API 호환을 위해 남기되 항상 1주 단위로 동작한다
- 현금 심볼: `KRW.CASH`, `USD.CASH`. 현금 잔고 키: `total_krw`, `krw_equivalent`, `rate_krw_per_usd`, `cash_krw`
- 매크로 지표（`MACRO_TICKERS`）: KOSPI `^KS11`, KOSDAQ `^KQ11`, S&P500 `^GSPC`, 나스닥선물 `NQ=F`, VIX `^VIX`, 미국10년물 `^TNX`, USD/KRW `KRW=X`, WTI `CL=F`, 금 `GC=F`
- 나스닥은 본장·야간을 가리지 않고 선물 `NQ=F` 를 쓴다. 미국 본장(평일 09:30~16:00 America/New_York)이면 본장 세션(09:30 ET 이후), 아니면 야간 세션(직전 18:00 ET 이후)의 변동을 `session` / `session_start` / `session_change` 키로 돌려준다. 세션 판정은 `src/data/yahoo_client/us_session.py`, 조회는 `macro.get_macro_indicators()` 가 담당한다. 한국 장중은 전부 야간 세션이며, 야간 선물 변동은 한국 장의 선행 신호다
- 섹터 RS 벤치마크는 `069500.KS`（KODEX 200）, 섹터 ETF 는 한국 상장 ETF（반도체·은행·자동차·증권·건설·철강·에너지화학·헬스케어·보험·운송·IT）

## 코딩 규약

### 툴 층 (tools/)
- 얇은 파사드. `src/data/` 의 함수를 re-export 만 한다
- 판단 로직을 포함하지 않는다
- `try/except ImportError` 로 `HAS_*` 플래그를 설정해 graceful degradation

### 에이전트 층 (.claude/agents/)
- `agent.md` — 역할·판단 프로세스·사용 툴·출력 방침
- `examples.yaml` — few-shot（intent → steps → reasoning）
- 에이전트가 판단·계산·정형화를 모두 담당한다

### 데이터 층 (src/data/)
- 데이터 취득은 반드시 `src/data/yahoo_client/` 경유（yfinance 를 직접 호출하지 않는다）
- Yahoo 는 한국 종목(.KS/.KQ)의 PER/PBR/EPS/BPS 를 주지 않는다. `get_stock_info` 가 `src/data/kr_valuation.enrich_stock_info()` 로 채우며, 공급자 추가 시 `kr_valuation/_*_provider.py` 에 `NAME` / `is_available()` / `get(symbol)` 을 갖춘 모듈을 두고 `PROVIDERS` 우선순위에 넣는다
- yahoo_client 는 모듈 함수（클래스가 아니다）
- 배당수익률 정규화: `_normalize_ratio()` 가 값 > 1 인 경우 100 으로 나누어 비율로 변환
- 데이터 모델 정의: `docs/data-models.md` 참조

### 공통 유틸리티 (src/data/)
- common.py, ticker_utils.py, portfolio_io.py 는 src/data/ 에 배치
- 판단 로직은 에이전트가 담당（src/data/ 는 순수한 데이터 조작만）

## 테스트

- `python3 -m pytest tests/ -q` 로 전체 테스트 실행（약 1,400 테스트, ~55초）
- `tests/conftest.py` 에 공통 픽스처: `stock_info_data`, `stock_detail_data`, `price_history_df`, `mock_yahoo_client`
- `tests/conftest.py` 에 autouse `_block_external_io` 픽스처: Neo4j/TEI/Grok 을 모든 테스트에서 자동 모킹
- `tests/fixtures/` 에 JSON/CSV 테스트 데이터（삼성전자 005930.KS 기반, 수치는 테스트용 가상값）
- 테스트 파일은 `tests/core/`, `tests/data/` 에 기능별로 배치

## Git 워크플로우

개발 플로우（Worktree 생성→설계→구현→테스트→리뷰→통합 시험→머지）는 [workflow.md](workflow.md) 참조.

- 브랜치명: `feature/kik-{NNN}-{short-desc}`
- 워크트리: `~/stock-skills-kik{NNN}`

## 파일 구성 가이드라인

### 크기 상한
- 프로덕션 코드: 400줄 이하 권장, 500줄에서 분할 검토
- 테스트: 600줄 이하 권장
- 에이전트 정의: agent.md 는 간결하게, examples.yaml 은 20예 정도

### 새 모듈 배치
- 툴 파사드 → tools/（데이터 조작만, 판단하지 않음）
- 에이전트 정의 → .claude/agents/<name>/（agent.md + examples.yaml）
- 데이터 취득/저장 → src/data/{yahoo_client,graph_store,graph_query,history,context}/
- 공통 유틸리티 → src/data/（common.py, ticker_utils.py, portfolio_io.py）
- 테스트 → tests/{core,data}/（src/ 와 1:1 대응）

## 문서 구성

- `docs/architecture.md` — 시스템 아키텍처（Agentic AI Pattern, Mermaid 다이어그램）
- `docs/neo4j-schema.md` — Neo4j 스키마 레퍼런스（노드 타입, 관계）
- `docs/data-models.md` — stock_info / stock_detail dict 스키마 정의

## 자동 컨텍스트 주입

- `src/data/context/` — 컨텍스트 취득 엔진（심볼 감지 + 그래프 상태 판정）
- `tools/graphrag.py` 의 `get_context()` 경유로 에이전트가 취득
- Neo4j 미접속 시 graceful degradation

## 툴 정의

- `config/tools.yaml` — 전체 툴의 함수명·역할·사용 시점을 일원 관리
- 툴(tools/)에 함수를 추가·변경한 경우 `config/tools.yaml` 도 갱신할 것
- 에이전트(agent.md)나 스킬(SKILL.md)은 툴 목록을 하드코딩하지 않고 `config/tools.yaml` 을 참조한다

## 외부 LLM 호출

- `call_llm()` 의 모델명을 하드코딩하지 않는다. `config/llm_routing.yaml` 을 Single Source of Truth 로 한다

## gitignore 대상

- `data/cache/` — 종목별 JSON 캐시（TTL 24시간）
- `data/watchlists/` — 워치리스트 데이터
- `data/screening_results/` — 스크리닝 결과
- `data/notes/` — 투자 메모 데이터
- 포트폴리오 데이터: `data/portfolio.csv`
