---
paths:
  - "tests/**/*.py"
  - "tests/conftest.py"
  - "tests/fixtures/**"
---

# 테스트 개발 규칙

## 테스트 실행

```bash
# 유닛 테스트（API key/네트워크 불필요）
python3 -m pytest tests/ -q                          # 전체 실행（약 1,400 테스트, ~55초）
python3 -m pytest tests/core/test_ticker_utils.py -v # 특정 모듈
python3 -m pytest tests/ -k "test_note"              # 키워드 지정

# Dry-run: routing.yaml + agent 정의 정합성 검증（< 1초, API key 불필요）KIK-746
python3 tests/e2e/run_e2e.py --dry-run

# 모의 E2E（pytest fixture 로 tools 층 stub 화, < 1초, API key 불필요）KIK-747
python3 -m pytest tests/e2e/test_mocked.py -q

# 실제 API E2E 테스트（실제 API 로 에이전트 동작을 검증, API key 필요）
python3 tests/e2e/run_e2e.py                         # 전체 시나리오（~25초）
python3 tests/e2e/run_e2e.py e2e_001                 # 특정 시나리오만
```

## Worktree 셋업（KIK-745）

개발용 worktree 는 전용 헬퍼 스크립트로 만들고, 개인 PF 를 흘리지 않는다:

```bash
bash scripts/setup_worktree.sh KIK-NNN feature-name
# → ~/stock-skills-kikNNN 에 전개, tests/fixtures/sample_portfolio.csv 를
#    data/portfolio.csv 에 복사. 개인 PF（실제 종목·실제 수량）는 건드리지 않는다.
```

⚠️ `cp ~/stock-skills/data/portfolio.csv` 는 금지. 실수로 커밋해 개인 PF 가 유출될 위험이 있으므로
   `tests/fixtures/sample_portfolio.csv`（범용 테스트 종목）를 사용할 것.

## 테스트 구조

- `tests/core/` — 코어 로직의 유닛 테스트（ticker_utils 등）
- `tests/data/` — 데이터 취득 층의 테스트（yahoo_client, grok_client, graph_store, note_manager 등）
- `tests/e2e/` — E2E 에이전트 테스트
  - `run_e2e.py` — 실제 API 시나리오 러너（`--dry-run` 으로 API 없이 검증）
  - `test_mocked.py` — pytest fixture stub 에 의한 모의 E2E（KIK-747）
  - `test_scenarios.yaml` — 시나리오 정의
- `tests/conftest.py` — 공통 픽스처（`_block_external_io` autouse 로
  Neo4j/TEI/Grok 을 전부 자동 모킹）
- `tests/fixtures/` — JSON/CSV 테스트 데이터
  - `stock_info.json` / `stock_detail.json` — 삼성전자 005930.KS 기반（수치는 테스트용 가상값）
  - `sample_portfolio.csv` / `sample_cash_balance.json` — KIK-745 worktree 용（KRW 기준, `total_krw`）

## 모킹 방법

### autouse 자동 모킹 (`_block_external_io`)

- Neo4j: `_get_mode()` → "off", `is_available()` → False
- TEI: `embedding_client.is_available()` → False
- Grok: `XAI_API_KEY` 삭제
- mode cache reset (KIK-743)

### 모의 E2E 의 stub 대상（test_mocked.py, KIK-747）

- `tools.llm.call_llm` → 고정 문자열 응답
- `tools.yahoo_finance.get_stock_info / get_stock_detail / screen_stocks /
  get_price_history / get_macro_indicators` → `tests/fixtures/*.json` 에서 반환
- `tools.grok.search_market / search_x_sentiment` → 고정 dict
- API key 전부 삭제（OPENAI/GEMINI/ANTHROPIC/XAI）

### sample fixture 이용

```python
SAMPLE_PORTFOLIO = REPO_ROOT / "tests/fixtures/sample_portfolio.csv"
positions = load_portfolio(str(SAMPLE_PORTFOLIO))  # 개인 PF 미참조
```

## 테스트 작성 시 주의점

- 각 테스트는 독립적으로 실행 가능해야 한다（외부 API 의존 없음）
- yahoo_client 호출은 반드시 모킹한다
- 테스트 데이터는 `tests/fixtures/` 의 기존 데이터를 재사용한다
- 종목 예시는 검증된 한국 티커（005930.KS, 000660.KS, 247540.KQ 등）또는 미국 티커만 사용한다
- 새 모듈에는 대응하는 테스트 파일을 만든다
- 새 에이전트 추가 시 `tests/e2e/test_mocked.py` 에 시나리오 추가（KIK-747）
- routing.yaml 변경 시 `tests/test_kik746_dry_run.py::test_routing_yaml_integrity_passes_currently` 로 검증
