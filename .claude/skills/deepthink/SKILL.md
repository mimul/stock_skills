---
name: deepthink
description: DeepThinking — 부족한 관점을 자율적으로 보완하고 시나리오 분기로 심층 분석한다. Evaluator-Optimizer 패턴.
user_invocable: true
---

# DeepThink

Evaluator-Optimizer 패턴으로 자율적으로 심층 분석한다. 일반 stock-skills 가 에이전트를 1회 기동해 답하는 것과 달리, DeepThink 는 **평가→개선 루프를 수렴할 때까지 자율적으로 반복**한다.

## 언제 사용하는가

- 「미중 관세 협상이 타결되면 PF 는 어떻게 돼?」→ 시나리오 분기 + PF 영향 계산
- 「재투자처를 제안해 줘」→ 후보 선정 + RSI 확인 + 시나리오 검증 + PF 타깃 대조
- 「6개월 뒤를 내다본 PF 설계」→ 매크로 시나리오 × 섹터 로테이션 × 통화 배분

일반 stock-skills 로 충분한 경우에는 쓰지 않는다. **복수의 불확실성이 얽힌 판단** 에 사용한다.

## 하네스 (강제 규칙)

아래는 생략·변경 불가.

```
⚠️ MUST: Step 2b 에서 GPT / Gemini / Grok + Claude 자신 4자를 반드시 실행. 생략 불가.
⚠️ MUST: 부족 리스트의 각 항목에 「무엇을 → 어느 LLM/툴로 → 왜」 를 부여한다.
⚠️ MUST: 수렴 조건을 만족할 때까지 자율적으로 루프를 계속한다. 매회 승인 대기는 불필요.
⚠️ MUST: 하네스 상한 도달 시에만 정지하고 사용자 승인을 요청한다.
```

## 실행 플로우

### Step 0: 시작 알림 + 실행 플랜 + 승인 대기

사용자에게 다음을 알린다:

```
🧠 DeepThinking 모드로 분석합니다
깊이: [shallow / medium / deep]（max N agents, M LLM calls）

📋 실행 플랜:
  Step 1: lesson 로드 → [테마에 따른 최초 분석 내용]（[사용 에이전트]）
  Step 2: 평가 + 4-Swarm 병렬 리뷰（2층 모델: 인프라 고정 + 추론 동적 할당）
  Step 3: 부족하면 추가 조사（[예상되는 추가 조사 내용]）
  → 수렴할 때까지 Step 2-3 자율 루프
  Step 5: 통합 리포트

계속할까요? [이대로 실행 / 플랜 수정 / 취소]
```

**⚠️ MUST (KIK-735): Step 1 시작 전에 preflight gate 를 반드시 통과한다.**

```python
from tools.preflight import run_preflight
result = run_preflight(domain="pf")  # PF 계열 테마. market/sector/stock 도 가능
if not result["passed"]:
    # violations 를 사용자에게 제시하고 abort
    raise SystemExit(f"Preflight failed: {result['violations']}")
```

이로써 cash_balance.json 미참조 / conviction 위반 / lot_size 오류를 코드 레벨에서 차단한다
(2026-04-27 PF 철저 리뷰에서 발생한 오추천 사고의 재발 방지). `run_preflight` 는
`data/cash_balance.json` 의 `total_krw` 를 읽어 `cash_krw` 를 산출하고,
`assert_pf_complete(positions_value_krw, cash)` 로 PF 완전성을 검증한다.

**실행 플랜은 테마에서 자동 생성한다 (제로샷).** 전형적인 예:

| 테마 | Step 1 | 예상되는 Step 3 |
|:---|:---|:---|
| 「PF 에서 재투자처 검토」 | HC + Researcher 로 PF 현황 + 시황 | 후보 RSI 확인, 시나리오 분기 |
| 「미중 관세 협상의 영향은?」 | Researcher 로 지정학 조사 | PF 종목별 감응도 계산 |
| 「6개월 뒤 PF 설계」 | HC + Researcher 로 매크로 조사 | 섹터 로테이션 × 통화 배분 |

깊이 선택 가이드:
- **shallow**: 1회의 추가 조사. 경미한 정보 부족 보완（max 3 agents, 5 LLM calls, 권장 출력 ~1500자）
- **medium**: 2-3회의 평가→개선 루프. 표준적인 심층 분석（max 6 agents, 12 LLM calls, 권장 출력 ~2500자）
- **deep**: 최대 5회의 루프. 철저한 분석（max 10 agents, 20 LLM calls, 권장 출력 ~4000자）

**⚠️ Step 0 에서만 사용자의 명시적 응답을 기다린다. Step 1 이후는 자율 루프.**
- 「이대로 실행」→ Step 1 로
- 「플랜 수정」→ 사용자 지시를 반영해 플랜을 다시 제시
- 「취소」→ DeepThink 를 중단하고 일반 모드로 복귀

### 사용 가능한 툴

**[config/tools.yaml](../../config/tools.yaml) 을 참조한다.** 전체 툴의 함수명·역할·사용 시점이 정의되어 있다.

**⚠️ MUST: 재투자·교체·후보 선정을 동반하는 테마에서는 `screen_stocks()` 로 데이터 기반으로 후보를 뽑는다. AI 의 지식 베이스에서 수동 선정해서는 안 된다.**

### Step 1: 최초 분석

**⚠️ MUST (KIK-738): lesson 은 전건 load 한 뒤 `filter_relevant_lessons()` 로 테마 관련분만 추출한다.**
전건을 그냥 훑어 읽는 것은 형식화를 부른다 (2026-04-27 / 2026-04-28 사고의 진짜 원인). 테마와 관련된 lesson 만
명시적으로 좁혀서, 그 내용을 이후 모든 단계에서 참조한다.

```python
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.notes import load_notes
from src.data.lesson_enforcer import filter_relevant_lessons

# 1. Lesson 전건 load → 사용자 의도와 관련된 것만 추출（KIK-738 hook）
all_lessons = load_notes(note_type='lesson')
user_input = '<USER_PROMPT_HERE>'  # 사용자의 이번 지시문
relevant_lessons = filter_relevant_lessons(user_input, all_lessons)

print(f'=== Lessons {len(relevant_lessons)}/{len(all_lessons)} relevant ===')
for n in relevant_lessons:
    print(f'[{n.get(\"date\",\"\")}] trigger={n.get(\"trigger\",\"(none)\")[:60]}')
    print(f'  expected_action: {n.get(\"expected_action\",\"(none)\")[:100]}')

# 관련 0건일 때의 fallback 전략:
#   (a) 해당 lesson 의 trigger 필드가 아직 백필되지 않음 → 최근 10건으로 대체
#   (b) 사용자 입력이 진짜 신규 패턴 (어느 trigger 와도 불일치)
# 어느 경우든 최근 10건으로 폴백한다. 백필 완료 후 (KIK-738 Phase 2)
# 관련 0건은 (b) 를 의미하게 된다.
if not relevant_lessons:
    print('[fallback] no trigger-match → recent 10 of', len(all_lessons))
    relevant_lessons = all_lessons[-10:]

# 2. 대상 종목의 thesis/observation（KIK-695）
import csv
with open('data/portfolio.csv') as f:
    symbols = [row['symbol'] for row in csv.DictReader(f)]
print(f'\n=== 전략 메모 ===')
for sym in symbols:
    notes = load_notes(symbol=sym)
    thesis = [n for n in notes if n.get('type') in ('thesis', 'observation')]
    if thesis:
        print(f'{sym}: {len(thesis)}건')
        for n in thesis[:2]:
            print(f'  [{n.get(\"type\")}] {n.get(\"content\",\"\")[:150]}')
"
```

`relevant_lessons` 를 이후 모든 단계에서 참조한다. Step 5 의 verify_lesson_cited 에
**이 동일한 리스트**를 인용 검증에 넘긴다 (일관성 보장).

다음으로 stock-skills 의 에이전트（Screener / Analyst / Health Checker / Researcher / Strategist）를 기동한다. 사용 가능한 에이전트는 [stock-skills routing.yaml](../stock-skills/routing.yaml) 을 참조.

### Step 2: 평가（자기 평가 + 3LLM 병렬 리뷰 + 반증→재플랜）

DeepThink 의 가치는 「왜 그 결론에 이르렀는가」의 사고 과정을 보여주는 데 있다.

#### 2a. 자기 평가

최초 분석 결과를 다음 관점으로 자기 평가한다:

| 관점 | 체크 내용 |
|:---|:---|
| 정보 충족 | 필요한 데이터가 갖춰졌는가（RSI? 실적 발표일? 센티먼트? 외국인/기관 수급?） |
| 시나리오 | 복수의 시나리오가 검토되었는가（낙관/비관/중립） |
| PF 정합 | 사용자의 PF 구성·타깃과 대조되었는가 |
| 반론 | Devil's Advocate 관점이 있는가 |
| lesson | 과거 lesson 과 모순되지 않는가（Step 1 에서 로드한 lesson 참조） |

#### 2b. 4-Swarm 병렬 리뷰（⚠️ 4자 전원 필수. 생략 불가）

**2층 모델: 인프라층（고정）+ 추론층（동적）으로 구성하는 Swarm.**

오케스트레이터가 GPT / Gemini / Grok 을 병렬 기동하고, Claude 자신도 오케스트레이터 층에서 직접 분석에 참여한다.

##### 인프라층（고정）— 물리적으로 대체 불가능한 능력

| LLM | 고정 역할 | 이유 |
|:---|:---|:---|
| Grok | X/실시간 시장 데이터 취득 | X Firehose 는 다른 LLM 으로 불가（하드 제약） |
| Gemini | Google 검색 + 대용량 컨텍스트 읽기 | Google Search Grounding 은 다른 LLM 으로 불가（하드 제약） |

##### 추론층（동적）— 테마에 따라 4자에 할당

| 역할 | 내용 |
|:---|:---|
| Devil's Advocate | 반증·리스크 지적·누락 검출 |
| Scenario Analyst | 시나리오 분기·감응도 분석·장기 추론 |
| Lesson Auditor | lesson 정합성·과거 학습과의 모순 검출 |
| Portfolio Aligner | PF 정합성·타깃 대조·통화(KRW/USD)/지역(kr/us) 배분 |

##### 적성 매트릭스（할당 판단에 사용）

| 역할 | GPT | Gemini | Grok | Claude |
|:---|:---|:---|:---|:---|
| Devil's Advocate | **최적** | 약함（지나치게 중립적） | 보통 | 가능 |
| Scenario Analyst | **최적** | 강함（장문 추론） | 표층적 | 가능 |
| Lesson Auditor | 가능 | **최적**（긴 컨텍스트） | 가능 | 강함 |
| Portfolio Aligner | 가능 | 가능 | 가능 | **최적** |

**⚠️ 하드 제약을 먼저 확인하고, 남은 추론 역할을 소프트 제약（적성）으로 할당한다.**

##### 테마별 할당 예

```
지정학 리스크:
  Grok   = [고정] X 시장 반응 + [동적] Devil's Advocate
  Gemini = [고정] Google 검색 + [동적] Scenario Analyst
  GPT    = [동적] Lesson Auditor
  Claude = [동적] Portfolio Aligner

실적 분석:
  Grok   = [고정] X 실적 반응 + [동적] （보조）
  Gemini = [고정] 실적 데이터 검증（DART 공시 포함）+ [동적] Lesson Auditor
  GPT    = [동적] Scenario Analyst
  Claude = [동적] Devil's Advocate

PF 재설계:
  Grok   = [고정] X 시장 평가 + [동적] Sentiment 보강
  Gemini = [고정] Google 검색 + [동적] Scenario Analyst
  GPT    = [동적] Devil's Advocate
  Claude = [동적] Portfolio Aligner
```

##### 호출 방법

| LLM | 호출 방법 |
|:---|:---|
| GPT | `call_llm('gpt', 'gpt-5.4', prompt, reasoning='high')` |
| Gemini | `call_llm('gemini', 'gemini-3-flash-preview', prompt, web_search=True)` or `call_llm('gemini', 'gemini-3.1-pro-preview', prompt)` |
| Grok | `tools/grok.py` 의 `search_x_sentiment()` / `search_market()` or `call_llm('grok', 'grok-4.20-0309-reasoning', prompt)` |
| Claude | 오케스트레이터 층에서 직접 실행（Agent 기동 불필요） |

#### 2c. 반증→재플랜

외부 리뷰의 반증을 바탕으로 최초 결론을 **수정 or 강화** 한다:

```
📊 DeepThink Step 2 완료（Agents: X/Y, LLM calls: A/B）

최초 결론: [최초 분석의 결론]

Swarm 할당: [테마명]
  GPT    = [고정: 없음] + [동적: 할당된 추론 역할]
  Gemini = [고정: Google 검색] + [동적: 할당된 추론 역할]
  Grok   = [고정: X 시장 데이터] + [동적: 할당된 추론 역할]
  Claude = [동적: 할당된 추론 역할]

반증:
  [Devil's Advocate 담당 LLM]: [반증 포인트]
  [Scenario Analyst 담당 LLM]: [시나리오 분기]
  [Lesson Auditor 담당 LLM]: [lesson 정합성]
  [Portfolio Aligner 담당 LLM]: [PF 정합성]

통합 결론:
  [4자의 지적을 바탕으로 오케스트레이터로서 통합적으로 판단한 결론]
  [「~는 타당하지만, ~의 지적을 반영해 ~로 수정한다」등]

재플랜:
  최초: [수정 전 제안]
  수정: [수정 후 제안]
  이유: [어느 지적이 어떻게 영향을 줬는가]
```

**⚠️ MUST: 통합 결론에서는 「각 LLM 의 지적을 판단에 어떻게 반영했는가」를 명시한다. 지적 나열로 끝내지 않는다.**

**평가 결과**: 부족 리스트를 작성한다（자기 평가 + 외부 리뷰 지적을 통합）.

**수렴 조건**（아래를 모두 만족하면 → Step 5 로）:
1. 5개 평가 관점이 모두 완료
2. 새로운 부족이 검출되지 않음

**종료 조건**（하나라도 해당 → 현시점 결과를 제시 + 사용자 승인 요청）:
1. max_iterations 도달
2. max_llm_calls 도달
3. max_wall_time_minutes 도달

### Step 3: 개선（Optimizer）— 자율 실행

부족 리스트에 따라 추가 에이전트/툴을 **자율적으로** 기동한다.

**⚠️ MUST: 각 부족 항목에 「무엇을 → 어느 LLM/툴로 → 왜」 를 부여한다.**

```
부족: 「X 센티먼트 미취득」
  → 무엇을: 005930.KS 에 대한 X 상의 투자자 평가
  → 어느 LLM: Grok search_x_sentiment("005930.KS", "삼성전자")
  → 왜: 후보의 시장 평가를 정성적으로 보완

부족: 「이벤트 시나리오 미검토」
  → 무엇을: 한국은행 금통위 / FOMC 최신 전망, USD/KRW 환율 방향
  → 어느 LLM: Gemini(web_search=True) 로 검색+추론
  → 왜: 다음 주 이벤트가 후보의 단기 주가 흐름에 영향

부족: 「RSI 미확인」
  → 무엇을: 후보 종목의 RSI(14)
  → 어느 툴: yahoo_finance.get_price_history + code interpreter
  → 왜: 과열권 매수 회피（lesson 참조）
```

**멀티 LLM 활용**（`config/llm_capabilities.yaml` 참조）:

| 용도 | 우선 LLM | 이유 |
|:---|:---|:---|
| **사실 수집（Google 검색）** | Gemini(web_search=True) | Google Search Grounding（하드 제약） |
| **X 센티먼트·실시간** | Grok(tools/grok.py) | X Firehose 액세스（하드 제약） |
| **반증·리스크 분석** | GPT(reasoning='high') | 비판적 사고·깊은 추론（소프트 제약: 최적） |
| **lesson 대조·장문 분석** | Gemini-Pro | 1M 컨텍스트（소프트 제약: 최적） |
| **PF 정합성·통합 판단** | Claude（자신） | PF 문맥 유지·오케스트레이션 |
| **철저 조사（업계 망라）** | Gemini Deep Research | 80-160 sources 자율 순회 + 인용 포함（KIK-731） |
| **복수 종목/테마 병렬** | Grok bulk_x / bulk_web | X firehose 병렬·속보 병렬（KIK-732） |

**⚠️ 하드 제약（물리적으로 불가능）을 먼저 고정하고, 소프트 제약（강점/약점）으로 추론 역할을 할당한다.**

#### Deep Research / Bulk Search 트리거 (KIK-731 / KIK-732)

사용자가 「**깊게**」「**철저하게**」「**DR 로**」「**제대로 파서**」라고 발화하거나,
분석 대상이 >5종목 / >3테마 횡단인 경우, Step 3 에서 다음을 제안한다:

```
🔍 Deep Research 를 기동할 수 있습니다
   - gemini.deep_research: Web 철저 조사（80-160 sources, 예상 $2.5, 5-10분）
     → 업계 전체상·규제 동향·DART/SEC 공시 등
   - grok.bulk_x_search: X 병렬 센티먼트（예상 $0.5-2.5, ~30초）
     → 투자자 센티먼트·$cashtag·속보
   실행할까요? [y/skip]
```

사용자가 `y` 면 실행. 완료 후 Layer 4 푸터에 기록:
```
💰 cost=$X.XX | 📚 sources=N | ⏱ duration=Xs
```

`config/tools.yaml` 의 `provider` / `when` / `strength` / `not_for` 로 **용도를 구분**:
- Web 망라 → `gemini.deep_research`（Google Search Grounding）
- X 내부 데이터 → `grok.bulk_x_search`（X firehose 독점）
- 속보 병렬 → `grok.bulk_web_search`

하드 제약: `deepthink_limits.yaml` 의 `tool_limits` 섹션（DR 월 10회/$30, bulk 월 20회/$10, 합산 $50）.
`DEEPTHINK_DR_ENABLED=off` 로 DR 즉시 정지.

### Step 4: 체크포인트（보고만 — 승인 대기가 아님）

개선 결과를 사용자에게 중간 보고한다. **보고 후, 부족이 있으면 자율적으로 Step 2 로 돌아간다.**

**아래 포맷을 엄격히 따를 것. 생략·변경하지 않는다.**

```
📊 DeepThink Step N/M 완료（Agents: X/Y, LLM calls: A/B）

중간 결과:
- [발견 1]
- [발견 2]
- [발견 3]

부족: [남은 부족 리스트 or "없음（수렴）"]
→ 자율 속행: [다음에 할 일] / 수렴: Step 5 로
```

사용자는 **멈추고 싶을 때만** 개입한다. 아무 말도 없으면 자율 루프를 계속한다.
사용자가 「멈춰」「방향 수정」이라고 말한 경우에만 정지한다.

### Step 5: 통합 리포트

**⚠️ MUST (KIK-735): 매매·트림·매도 제안을 포함하는 경우, Step 5 직전에 preflight 재검증.**

```python
from tools.preflight import run_preflight
proposed = [("trim", "NVDA", 3), ("sell", "035420.KS", 10)]  # 예
result = run_preflight(domain="pf", proposed_actions=proposed)
if not result["passed"]:
    # conviction 위반 / lot_size 오류 → 추천을 출력하기 전에 수정
    raise SystemExit(f"Preflight failed at Step 5: {result['violations']}")
```

한국·미국 모두 매매 단위는 1주이므로 `assert_lot_size` 는 수량이 양의 정수인지만 검증한다.

**⚠️ MUST (KIK-738): Step 1 에서 추출한 `relevant_lessons` 를 최종 제안문에서 **그대로 인용**하고 있는지 검증.**

인용 0건은 「lesson 형식화」의 전형적 패턴 (2026-04-27 철회 로그 / 2026-04-28 META 추천 실수).
Step 5 출력 전에 반드시 아래를 실행하고, lesson 이 인용되지 않았으면 제안을 **다시 쓴다**:

```python
from src.data.lesson_enforcer import verify_lesson_cited

final_proposal_text = "<이그제큐티브 서머리 + Swarm 통합 + 상세 의 본문>"
ok, missing_lesson_ids = verify_lesson_cited(final_proposal_text, relevant_lessons)
if not ok:
    # missing_lesson_ids 의 lesson 에서 expected_action / key_kpis 를 뽑아
    # 이그제큐티브 서머리 본문에 포함해 다시 생성한다.
    raise SystemExit(
        f"Step 5 lesson citation failed: {missing_lesson_ids} are not cited in proposal. "
        "제안 텍스트에 해당 lesson 의 expected_action/key_kpis 를 그대로 인용한 뒤 다시 출력할 것."
    )
```

추가로, **Deep Research / bulk_search 를 실행한 경우에는 DR 의 "불채택" 종목 리스트가**
**최종 제안에 섞여 들어가지 않았는지 cross-check**:

```python
import re

# DR 리포트 본문 (Step 3 에서 취득한 text) 에서 불채택 종목을 동적으로 추출.
# 규칙: 「보류」「불채택」「제외」「리젝트」「reject」를 포함하는 섹션 안의
# 티커풍 토큰 (대문자 2-5자 or 6자리.KS/.KQ 한국 종목코드) 을 집는다.
def _extract_dr_rejected(dr_text: str) -> list[str]:
    if not dr_text:
        return []
    pattern = r"(?:보류|불채택|제외|리젝트|reject)[^\n]{0,400}"
    rejected: set[str] = set()
    for match in re.finditer(pattern, dr_text):
        sect = match.group(0)
        for sym in re.findall(r"\b([A-Z]{2,5}|\d{6}\.K[SQ])\b", sect):
            rejected.add(sym)
    return sorted(rejected)

dr_text = "<Step 3 에서 취득한 DR 본문 (출력 텍스트 전체)>"
dr_rejected = _extract_dr_rejected(dr_text)  # 예: ["META", "VST", "035720.KS"]
for sym in dr_rejected:
    # plan 에 등장하지만 「DR 불채택」「DR rejected」같은 명시적 반대 논증이 함께
    # 포함되어 있지 않으면 abort
    if sym in final_proposal_text and not re.search(
        rf"{sym}.{{0,80}}(불채택|rejected|보류|제외)", final_proposal_text
    ):
        raise SystemExit(
            f"DR cross-check failed: '{sym}' is in DR rejected list but is "
            "referenced in the proposal without explicit rejection rationale. "
            "DR 에서 불채택 판정된 종목을 편입하려면 그 반대 근거를 명시할 것."
        )
```

`_extract_dr_rejected()` 는 DR 리포트 포맷에 의존하는 best-effort 추출이다.
DR 이 새 포맷이 되면 정규식을 확장할 것. 테스트는
`tests/data/test_lesson_enforcer.py::TestStep5HookScenarios` 에 정합 패턴이 있다.

**⚠️ MUST (KIK-739): 제안 출력 직전에 Layer 5 (Cited Sources) 를 생성해 본문 말미에 추가.**

「근거로 삼은 note 의 가시화 + 신선도 마커」로, 오래된 정보가 쓰레기 데이터가 되는 것을 막는다
(2026-04-28 세션에서 드러난 「lesson 이 인용되지 않는다」「ATH 접근을 놓친다」문제에 대한 대응).

```python
from src.data.citation_formatter import format_cited_sources

# verify 에서 실제로 인용된 것으로 판정된 lessons 를 citation 후보로
cited_lessons = [l for l in relevant_lessons if l.get("id") not in missing_lesson_ids]
# 대상 종목의 thesis (Step 1 에서 로드됨) 중 제안문에 symbol 이 등장하는 것을 cited 로
cited_theses = [
    t for t in all_theses
    if (t.get("symbol") or "") and t["symbol"] in final_proposal_text
]
# 각 인용 노트가 제안의 어디에 쓰였는지 1줄로 메모.
# key 는 note['id'] (실제 저장 형식: e.g. 'note_2026-04-24_portfolio_a1b2c3d4')
used_for_map = {
    cited_lessons[0]["id"]: "Cash 15-20% 판정",
    cited_lessons[1]["id"]: "매도 대상 제외",
    # ... 각 cited_lessons / cited_theses 에서 id 를 꺼내 매핑
}

citation_block = format_cited_sources(
    cited_lessons, cited_theses, used_for_map=used_for_map,
)
final_proposal_text = final_proposal_text.rstrip() + "\n\n" + citation_block
```

`format_cited_sources` 의 신선도 마커 규칙:
- `permanent` 태그 → 🟢 (항상 fresh, 영속 규칙)
- `seasonal` (or 태그 없음) → 0-30일 🟢 / 31-90일 🟡 / 91일+ 🔴
- `expired` → 출력에서 자동 제외
- thesis 에 conviction_override → 🔒 (신선도 무시)

인용 0건은 **lesson 형식화의 전형** (2026-04-27 철회 로그의 패턴) — 위의 verify_lesson_cited
가 abort 하므로, 여기에 도달한 시점에는 반드시 1건 이상 citation 이 있는 상태다.

**이그제큐티브 서머리 선행의 3부 구성（서머리, 논의 통합, 상세）으로 출력한다.**

**아래 포맷을 엄격히 따를 것. 생략·변경하지 않는다.**

```
■ 이그제큐티브 서머리
[결론을 3-5줄로. 추천 액션 + 근거 요점 + 주요 수치]

■ Swarm 논의 통합
[4자의 지적을 바탕으로 한 통합적 판단 이유]
  - [LLM-A]는 「~」라고 지적 → [채택/기각/부분 채택]한 이유
  - [LLM-B]는 「~」라고 분석 → [결론에 어떻게 반영했는가]
  - [LLM-C]는 「~」를 보고 → [판단에 어떻게 영향을 줬는가]
  - Claude（자신）는 「~」라고 평가
  → 이를 종합해 [최종 판단 근거]

■ 상세
  시나리오 분석:
    [낙관/중립/비관의 확률과 영향]
  포트폴리오 영향:
    [구체적인 수치 변화（원화 기준, USD 자산은 USD/KRW 환율 반영）]
  근거 데이터:
    [사용한 지표·소스]
  추천 액션:
    [구체적인 액션 리스트（「아무것도 하지 않음」포함）]
```

**⚠️ MUST: 이그제큐티브 서머리만으로 판단할 수 있는 입도로 만든다. 상세는 「왜 그렇게 판단했는가」의 근거.**
**⚠️ MUST: Swarm 논의 통합에서는 각 LLM 의 지적을 「채택/기각/부분 채택」판단과 함께 제시한다. 지적 나열로 끝내지 않는다.**

## 하네스 제약

`deepthink_limits.yaml` 에 따라 폭주를 방지한다:

- 상한 도달 시: 루프 정지 → 현시점 결과 제시 → **속행에는 사용자 승인이 필요**
- 진행 상황은 각 단계에서 표시: 「Agents 4/6, LLM calls 8/12」

## 진행 표시 포맷

**이 포맷을 엄격히 따를 것. 생략·변경하지 않는다.**

단계 시작 시:
```
🔍 DeepThink Step N: [단계명]
   [실행 중인 LLM/툴명] 으로 [무엇을 하고 있는가]...
```

단계 완료 시:
```
✅ DeepThink Step N 완료
   발견: [주요 발견을 1-2줄로]
   다음 단계: [다음에 할 일]
```

## References

- 하네스 제약: [deepthink_limits.yaml](./deepthink_limits.yaml)
- LLM 선택: [llm_capabilities.yaml](../../config/llm_capabilities.yaml)
- 일반 모드: [stock-skills SKILL.md](../stock-skills/SKILL.md)
