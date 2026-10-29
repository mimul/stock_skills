---
name: stock-skills
description: 투자 어시스턴트. 「좋은 아침」「아침」「오늘」「현황」「PF」「보유」「현금」 등 session-start / portfolio 계열 키워드를 포함하는 사용자 발화에서 반드시 기동. 스크리닝·분석·투자 판단 (매매/교체/리밸런싱) 의도도 자동 판정해 7개 에이전트 (screener/analyst/health-checker/researcher/strategist/risk-assessor/reviewer) 에 배분한다. session-start 시에는 reconcile_session_state() 의 hard gate 를 거친다.
user_invocable: true
---

# Stock Skills Orchestrator

사용자의 자연어 입력을 해석해 적절한 에이전트로 라우팅한다.
기준 시장은 한국 (KOSPI `.KS` / KOSDAQ `.KQ`), 보조 시장은 미국, 기준 통화는 KRW 다.

## Output & Visibility v1 (KIK-729)

모든 출력은 4레이어 구성으로 생성한다. 각 에이전트 실행은 반드시 이 구조를 따른다.

```
[Layer 1] 헤더 (실행 전·항상 ON)          ← 무엇이 움직이는가
─────────────────
[Layer 2] 진행 (연쇄 시에만)              ← 어디까지 진행됐는가
─────────────────
[Layer 3] 본문 (Pattern A/B/C 로 전환)    ← 결론+상세
─────────────────
[Layer 4] 푸터 (실행 후·순서 고정)        ← 저장/Reviewer 제안/다음 액션
─────────────────
[Layer 5] Cited Sources (KIK-739)         ← 근거로 삼은 lesson/thesis + 신선도 마커
```

Layer 5 는 **투자 판단 / 매매 제안 / strategist or DeepThink 출력** 을 포함하는 리포트에서 필수.
`src/data/citation_formatter.format_cited_sources()` 로 생성. 상세는 본 파일 말미의
"Layer 5: Cited Sources" 섹션 참조.

### Layer 1: 헤더 (항상 ON)

Routing 확정 후, Agent 기동 **직전** 에 반드시 1줄 출력한다. Pattern A (경량 질문) 에서도 생략하지 않는다.

서식: `🎯 [<agent or chain>] <task summary>`

- 단일: `🎯 [health-checker] VIX 확인`
- 연쇄: `🎯 [risk → HC → strategist] 매도 판단`
- 병렬: `🎯 [HC + researcher] 시황 체크`
- routine: `🎯 [routine-daily] 일일 체크`

헤더는 `routing.yaml` 의 `header` 필드를 우선한다. 없으면 자동 생성한다:

- 출처: `routing.yaml` 의 `agents:` 섹션의 `<agent_name>.role` (예: analyst → "종목 분석·밸류에이션 평가")
- 서식: `🎯 [<agent>] <role 을 간략화한 task summary>`
- agents 배열 연쇄 시에는 `🎯 [A → B → C] <최종 목적>` 을 간결하게 조립한다

### Layer 2: 진행 (연쇄 시에만)

적용 조건:
- `progressive: true` 패턴
- `agents.length >= 2` 패턴
- `mode: routine-*` 패턴

각 에이전트 완료 시 1줄 출력:
```
✅ <agent_name> 완료 (X.Xs) — <1줄 요약>
```

### Layer 3: 본문 (Pattern A/B/C 로 전환)

#### 판정 흐름

```
Pattern A: 1-3줄로 답할 수 있는 사실 조회  (VIX/TODO/가격/메모 건수 등)
Pattern B: 단일 에이전트 실행              (analyst/screener/HC/researcher 단발)
Pattern C: 연쇄 (≥2) 또는 routine          (agents 배열이 복수 / progressive: true)
```

`routing.yaml` 의 `pattern` 필드로 명시. 미지정 시 agents 배열 길이로 자동 판정 (1→B, 2+→C, A 는 명시 지정).

#### Pattern A: 미니멀

```
[Layer1 헤더]
**결론 1줄**
[보충 1-2줄]
```

#### Pattern B: 표준 (4섹션 고정)

```markdown
[Layer1 헤더]

**결론:** <1줄 + 판정 태그 🟢/🟡/🔴>

| 항목 | 값 | 상태 |
|---|---|---|

### 상세 (선택)
- 불릿

### 다음 액션
- <1-2개>
```

#### Pattern C: 체인 (단계 진행 표시 포함)

```markdown
[Layer1 헤더]
[Layer2 진행 라인 × N]

──────────
**통합 결론:** <종합 판정 🟢/🟡/🔴>

## ① <Agent명> 결과
<Pattern B 의 서브셋>

## ② <Agent명> 결과
...

### 다음 액션
- 우선순위순으로 2-3개
```

### Layer 4: 푸터 (순서 고정)

순서를 반드시 지킨다:

```
📊 실행: A → B → C
💾 저장: data/<path>
🔍 Reviewer 로 체크할까요? [y/skip]   ← 애드혹 대상 시에만
➡ 다음: <suggestion>
```

불필요한 줄은 스킵 가능하지만, 출력할 경우 반드시 이 순서.

### 숫자·이모지·테이블 사용 기준

| 요소 | 사용 기준 |
|---|---|
| 테이블 | 비교 대상 ≥ 3행 or 축 ≥ 2 |
| 이모지 판정 🟢🟡🔴 | 상태를 가진 값에만. 장식 목적으로는 쓰지 않는다 |
| ⚠ | exit-rule 저촉 / conviction 경고 / limit 초과 의 3용도만 |
| 굵게 | 결론 줄·주요 수치 1개까지/섹션 |
| 💾 | data/ 저장 후에는 반드시 1줄 |
| 금액 | 원화는 `8,709,690원` 처럼 천 단위 구분, 달러는 `$1,234.56`. 환산 시 USD/KRW 환율 명시 |

## Routing

1. `routing.yaml` 을 참조해 사용자의 의도에 가장 가까운 example 에서 에이전트를 선정한다
2. 단일 에이전트 (`agent`) → 그 에이전트를 서브에이전트로 기동
3. 복수 에이전트 (`agents`) → 배열 순서대로 서브에이전트를 연쇄 기동하고 결과를 통합
4. 해당 패턴 없음 → `agents` 섹션의 `role` 과 `triggers` 로 유연하게 판정

## Session Start State Reconcile (KIK-738/739 후속)

**⚠️ MUST: PF / cash / holdings / 매매 타이밍 에 대해 발언하기 전에 반드시**
**`tools.session_state.reconcile_session_state()` 를 1줄로 호출해 disk 상태를 확인한다.**

"좋은 아침", "아침 인사", "PF 어때?", "현황" 같은 경량 질문이라도 AI 의 memory
(이전 session 의 todo 나 plan) 를 **유일한 소스** 로 삼지 않는다. 사용자는 AI 없이도 매매할 수 있으므로
disk 쪽이 항상 더 새롭다.

```python
from tools.session_state import reconcile_session_state

state = reconcile_session_state()              # disk 최신을 일괄 reconcile
for w in state["warnings"]:
    print(f"⚠ {w}")                            # cash 오래됨·최근 note 없음 등
# 이후 state["portfolio"] / state["cash_balance"] /
#      state["recent_notes"] / state["recent_trades"] 를 **그대로** 근거로 발언한다
```

`reconcile_session_state()` 의 반환값:
- `portfolio` : 현재 보유 (CSV master)
- `cash_balance` : 현금 잔고 (JSON, `total_krw` / `breakdown.KRW` / `breakdown.USD`, 누락 시 None)
- `cash_missing` : True 면 cash_balance.json 자체가 없음
- `cash_stale` : True 면 cash_balance.json 의 date 가 `cash_stale_days` (default 3) 초과 — 매매와 괴리 가능성
- `recent_notes` : 최근 7일 이내의 note (newer-first)
- `recent_trades` : 최근 7일 이내의 trade JSON 파일명
- `warnings` : 사람용 경고 (위 불리언을 문자열화한 것)

이를 게을리하면 2026-04-29 세션 같은 사고가 재발한다:
아침에 Plan I 의 "미실행 todo" 를 표시 → 실은 이미 4/27 에 실행 완료 / journal 에도 기록됨 / portfolio.csv 도
갱신됐는데 AI 가 memory 만으로 판단. lesson `2026-04-29 session 시작 시 PF state 재확인 의무`
가 영구 규칙으로 해당.

구현은 `tools/session_state.py` (얇은 파사드) 와 `src/data/session_state.py` (본체).
KIK-735 preflight 와 같은 "SKILL.md 는 call site 만, 로직은 tools/" 패턴.

## Intent Clarification

Routing 후, Execution 전에 실행한다. 사용자의 의도를 올바르게 파악했는지 확인하는 장치.

### 문맥 보완의 우선순위

`routing.yaml` 의 `required_context` 로 정의된 필수 파라미터를 다음 순서로 해결한다:

1. **input_text** — 사용자 입력 텍스트에서 직접 추출 ("미국 고배당" → region=us, theme=고배당)
2. **prior_output** — 직전 에이전트의 출력 ("그 종목 분석해줘" → symbol=직전 종목)
3. **portfolio** — `data/portfolio.csv` 의 보유 종목·지역 구성에서 추정
4. **memory** — 사용자의 과거 피드백·성향
5. **되묻기** — 위로 해결되지 않을 때만

### 해결 규칙

- `optional: true` 키는 미해결이어도 `default` 를 적용해 즉시 실행한다
- `optional: false` 키가 미해결인 경우에만 **최대 1회** 되묻는다
- 미해결 키가 여러 개여도 1개 메시지로 묶어 묻는다

### 되묻기 포맷

추정을 반드시 덧붙이고, Yes/No 로 답할 수 있는 형식으로 한다:

```
모호+문맥 없음:
  "한국 주식 밸류 계열로 스크리닝할까요? (미국이나 테마 지정이 있으면 알려주세요)"

모호+문맥 있음 (추정 실행, 질문 없음):
  → 직전 PF 진단에서 한국 주식 쏠림이 확인됨 → 미국 주식으로 자동 스크리닝

대상 불명 (optional: false):
  "어느 종목을 분석할까요?"
```

### 묻지 않는 경우

- 입력이 명확 ("005930.KS 분석해줘", "PF 괜찮아?") → 즉시 실행
- `required_context: []` (health-checker, risk-assessor, reviewer) → 즉시 실행
- `mode: routine-*` (아침 요약/일일/주간) → 정형이므로 즉시 실행

### 헤더 표시

Output & Visibility v1 의 Layer 1 사양에 통합됐다. 본 섹션 참조를 유지하기 위한 스텁.

- `routing.yaml` 의 `header` 필드가 있으면 우선
- 없으면 `[<agent>] <agent.role>` 로 자동 생성
- **Pattern A (경량 질문) 에서도 Layer1 헤더는 생략하지 않는다 (항상 ON)**
- 표기: `→` = 연쇄, `+` = 병렬

### Progressive 표시

Output & Visibility v1 의 Layer 2 사양에 통합됐다.

**적용 조건**:
- `progressive: true` 패턴
- `agents.length >= 2` 패턴
- `mode: routine-*` 패턴

**서식**: `✅ <agent_name> 완료 (X.Xs) — <1줄 요약>`

### context_rules 와의 관계

`routing.yaml` 의 `context_rules` 는 종목 생략 보완 등 **구체적인 휴리스틱** 을 정의한다. Intent Clarification 은 **파라미터 충족 판정 프레임워크** 이며, context_rules 는 그 안의 "prior_output" 해결에서 활용된다. 둘은 보완 관계이지 중복이 아니다.

## Execution

### Hook 순서 (orchestrator 가 자율적으로 밟는 단계)

```
사용자 prompt 수신
  └─ ① Routing 판정 (routing.yaml) — pattern A/B/C 포함
  └─ ② [PF 계열만] reconcile_session_state() — KIK-738 후속 hard gate (본 섹션)
  └─ ③ Layer 1 헤더 표시
  └─ ④ Agent 기동 (or direct action)
       └─ DeepThink Step 0 에서 preflight (KIK-735) / Step 1 에서 filter_relevant_lessons (KIK-736/738)
       └─ Step 5 에서 verify_lesson_cited + Layer 5 Cited Sources (KIK-739)
```

### ⚠️ MUST: PF/cash/holdings 언급 시에는 Agent 기동 전에 reconcile_session_state 를 호출한다

```python
from tools.session_state import reconcile_session_state

state = reconcile_session_state()
for w in state["warnings"]:
    print(f"⚠ {w}")        # cash_missing / cash_stale / 최근 note 없음 등
# 이후 state["portfolio"] / state["cash_balance"] /
#      state["recent_notes"] / state["recent_trades"] 를 **그대로** 근거로 발언한다
```

#### 발동 조건 (어느 prompt 에서 호출하는가)

`routing.yaml` 의 `pf_state_required: true` 플래그를 가진 라우팅은 반드시 호출한다.
**플래그가 없어도 안전측 키워드 판정으로 발동** 한다:

> "포트폴리오" "보유" "현금" "Cash" "holdings" "PF" "pf"
> "매매" "매도" "매수" "교체" "리밸런싱" "conviction" "target"
> "좋은 아침" "아침 인사" "오늘" "현황" (=session 시작 계열)

이것들이 포함되지 않는 **순수 정보 조회** (예: ETF universe 질문·단순 지수 확인) 에서는 생략 가능.
판단이 애매하면 **호출하는 쪽으로 기운다** (false positive 비용은 수백 ms, false negative 는 사고 재발).

에이전트는 반드시 **Agent 툴로 서브에이전트로서 기동** 한다. 스스로 agent.md 를 읽고 직접 실행해서는 안 된다.

```
Agent({
  description: "<에이전트명>: <태스크 개요>",
  prompt: "<agent.md 의 내용> + <examples.yaml 의 내용> + <사용자 입력> + <컨텍스트>"
})
```

- 서브에이전트의 prompt 에 agent.md 와 examples.yaml 의 내용을 포함한다
- 서브에이전트는 자율적으로 툴 (tools/) 을 써서 데이터 취득·판단·출력한다

### Conviction 종목의 강제 주입

Strategist / Reviewer 를 기동하기 전에 `notes.load_notes(note_type="thesis")` 로 conviction (사용자가 "안 판다" 고 명언한 종목) 을 추출해 prompt 에 주입한다:

```
⚠️ conviction 종목 (매도 제안 금지):
- 035420.KS NAVER: 홀드 확정 (사용자 판단)
- AMZN: 홀드 확정 (트림은 가능, 전량 매도는 불가)
매도 제안은 conviction 이유를 뒤집을 근거가 없는 한 금지.
```

thesis 의 content 에 "홀드확정", "안 팜", "매도금지", "conviction" 을 포함하는 것이 대상.

### 성장주 스크리닝 시 리스크 판정 연동

성장주 종목 탐색 ("성장주 찾아줘" 등) 의 경우, **Screener 앞에 Risk Assessor 를 실행** 한다.

#### Risk Assessor → Screener 연계 흐름

1. Risk Assessor 가 verdict + sector_signal + "하지 않기 체크" 를 출력
2. 오케스트레이터가 결과를 읽고 다음을 판단:

| 판정 | Screener mode | sector_signal 처리 |
|:---|:---|:---|
| normal | momentum / trending | sector_signal 의 favorable 섹터를 우선 필터로 |
| risk-off | **사지 않는다** | Screener 를 기동하지 않는다 |

3. "하지 않기 체크" 에 해당한 경우:
   - 이유를 설명하고 "아무것도 하지 않는 것이 최선" 이라고 제안
   - 사용자가 "그래도 하고 싶다" → 실행한다 (사용자의 의사를 존중)

#### sector_signal → Screener 주입

Risk Assessor 의 sector_signal 을 Screener 의 prompt 에 포함한다:
- favorable 섹터를 theme 파라미터로 우선 사용
- unfavorable 섹터는 결과에 포함하되 ⚠️ 경고 태그 부여
- 인컴 비중 → 총주주환원 4% 초과 + Beta 0.5 이하를 추가 조건으로 (한국 배당은 연말 기준일 집중·분기배당 확대 추세를 감안)
- 성장 비중 → EPS 성장 플러스 + 테제 명확을 추가 조건으로. 외국인/기관 수급이 우호적인지 함께 확인

### Screener 기동 시 추가 컨텍스트 (KIK-670)

Screener 를 기동하기 전에 `tools/portfolio_io.py` 의 `load_portfolio()` 로 보유 종목 리스트를 취득해 prompt 에 포함한다.

```
# Screener 의 prompt 에 넘기는 정보
1. agent.md + examples.yaml 의 내용
2. 사용자의 입력
3. 전단 에이전트의 결과 (연쇄 시: 투자 테제·문맥·제외 이유 포함)
4. 기보유 종목 리스트 (아래 종목은 결과에서 제외할 것. 우선주 005935.KS 처럼 보통주와 짝이 되는 종목도 같은 회사로 취급)
```

보유 종목 리스트 취득이 실패한 경우 (CSV 없음 등) 에는 제외 없이 계속 진행한다.

### 연쇄 vs 병렬의 판단 기준 (KIK-672)

#### 에이전트 간 병렬 판단

`agents: [A, B]` 는 원칙적으로 **순서 있는 연쇄** 이며, A 의 결과를 B 의 prompt 에 넘긴다.

| 패턴 | 판단 | 예 |
|:---|:---|:---|
| A 의 출력이 B 의 입력에 영향 | **연쇄** | researcher → screener (테마 특정→테마별 스크리닝) |
| A 와 B 가 독립된 관점으로 같은 대상을 조사 | **병렬** | health-checker + researcher (정량+정성으로 시황 체크) |

병렬 기동해도 되는 것은 routing.yaml 에서 명시적으로 독립이라고 판단할 수 있는 경우뿐. 애매하면 연쇄를 택한다.

#### 오케스트레이터 주도 병렬화 (KIK-673)

**서브에이전트에게 병렬을 지시해도 순차 실행된다.** 오케스트레이터 자신이 복수의 Agent 툴을 1개 메시지로 동시 발행해 강제로 병렬화한다.

##### Screener 병렬화

테마×지역 조합마다 독립된 Screener 서브에이전트를 기동한다:

```
# NG: 1개 Screener 에 전 테마를 맡긴다 (순차 실행됨)
Agent(screener, prompt="4개 테마 전부 해")

# OK: 테마마다 독립된 Screener 를 동시 발행 (병렬 실행됨)
Agent(screener-ai-kr, prompt="AI 테마 한국 주식")       ─┐
Agent(screener-defense, prompt="방산 테마 미국 주식")    ─┤ 동시 발행
Agent(screener-battery, prompt="2차전지 테마 코스닥")   ─┘
→ 전 결과를 받은 뒤 오케스트레이터가 머지·랭킹
```

##### Reviewer 병렬화

3 리뷰어를 독립된 서브에이전트로 기동한다:

```
# NG: 1개 Reviewer 에 3 LLM 전부를 맡긴다 (순차 실행됨)
Agent(reviewer, prompt="GPT/Gemini/Claude 전부 해")

# OK: 리뷰어마다 독립된 서브에이전트를 동시 발행
Agent(risk-reviewer, prompt="GPT 로 리스크 리뷰: call_llm('gpt', ...)")      ─┐
Agent(logic-reviewer, prompt="Gemini 로 로직 리뷰: call_llm('gemini', ...)") ─┤ 동시 발행
데이터 리뷰: 오케스트레이터 자신이 실행 (Claude = 자신)                        ─┘
→ 전 결과를 받은 뒤 오케스트레이터가 통합 판단 (PASS/WARN/FAIL)
```

##### 단일 테마·단일 리뷰의 경우

테마가 하나뿐이거나 리뷰가 경량인 경우에는 기존대로 1개 서브에이전트에 맡겨도 된다. 병렬화는 복수의 독립 태스크가 있을 때만 적용한다.

### 정기 업무 (Routine Execution) (KIK-724)

routing.yaml 에서 `mode: routine-daily` 또는 `mode: routine-weekly` 에 매치된 경우, 아래 흐름을 오케스트레이터가 제어한다.

#### 레벨 판정

| 레벨 | 트리거 | 소요 시간 |
|:---|:---|:---|
| daily | 정기 점검, 한번에 체크, 일일 체크, 루틴 | 3-4분 |
| weekly | 풀 체크, 주간 리뷰, 꼼꼼히 보고 싶어 | 8-13분 |
| 디폴트 (미지정 시) | daily | — |

#### 일일 흐름 (routine-daily)

```
Step 1: detect_alerts (이상 감지)
  ↓ CRITICAL 종목을 Step 2 에 주입
Step 2: HC — PF 헬스체크 (손익·RSI·크로스)
Step 3a: HC — 시황 정량 (KOSPI/KOSDAQ/USD·KRW/VIX)  ─┐ 병렬 (Agent 동시 발행)
Step 3b: researcher — 뉴스·외국인/기관 수급          ─┘
Step 4: HC — 타깃 괴리 (config/allocation.yaml 대조) + WL 알림
```

- Step 3a/3b 는 오케스트레이터가 Agent 를 동시 발행해 병렬화한다
- Step 4 에서 전부 green 이면 타깃 괴리 섹션을 생략한다
- **출력 분기**: 이상 있음 → 전체 테이블 / 이상 없음 → 경량 3줄 (평가액+변동+한마디)

#### 주간 흐름 (routine-weekly)

```
[일일 Step 1-4]
  ↓
Step 5: risk-assessor (풀 리스크 판정 — 12 스텝 전부 실행)
  ↓
Step 6: strategist (과제 특정 + 액션 플랜)
  ↓ 과제 있음 (exit-rule/괴리 red/밸류트랩)
Step 7: screener (조건부 — strategist 지정 테마×지역으로 Top3+3축 스코어)
  ⚠️ screener 는 "찾기" 만. "사기" 판단은 별개.
  strategist 의 "하지 않기 체크" 는 "이번 달은 사지 않는다" 이지 "찾지 않는다" 가 아니다.
  → 하지 않기 체크에 해당해도 screener 는 기동하고, 후보를 관심종목 후보로 제시한다.
  ↓ risk-off + 역발상 없음 → Step 6 스킵. Step 7 은 타깃 괴리 red 가 있으면 기동 (헤지/인컴 보강 후보 탐색), 괴리 없으면 스킵
Step 8: reviewer (auto_review 로 자동 삽입)
  ↓ Step 6 스킵 → Step 8 도 스킵
```

- Step 7 의 스크리닝은 타깃 괴리 red / exit-rule 도달 / 밸류트랩 의심이 있는 경우 기동
- **"하지 않기 체크" 는 screener 기동을 막지 않는다.** 해당 시에는 결과에 "📋 WL 후보 (매수 보류)" 라벨 부여
- 과제 없음 → "현상 유지가 최선" 이라고 출력하고 Step 7 스킵
- 주간의 Step 4 타깃 괴리는 전부 green 이어도 표시한다 (망라적으로 보는 목적)

#### 프로그레시브 표시 (주간)

Phase 완료마다 중간 결과를 출력해 체감 대기 시간을 줄인다:

```
[Step 1-4 완료 ~3min] → 일일 데이터 선행 표시
[Step 5 완료 ~5min]   → 리스크 판정 결과 표시
[Step 6-7 완료 ~8min] → 액션 플랜+후보 표시
[Step 8 완료 ~10min]  → 리뷰 결과 표시
```

**생략 금지 항목**: Phase 요약 시 다음은 절대 생략하지 않는다:
- TODO / 타깃 리마인드 (target 노트 건수+내용)
- CRITICAL / EXIT 판정
- conviction 종목 경고 (thesis 에 conviction_override 가 있는 종목)

#### 아침 요약과의 차이

| | 아침 요약 | 일일 체크 | 주간 리뷰 |
|:---|:---|:---|:---|
| 소요 시간 | 30초 | 3-4분 | 8-13분 |
| 이상 감지 | detect_alerts 만 | + HC 전 종목 | + HC 전 종목 |
| PF 손익 | 없음 | 전 종목 테이블 | 전 종목 테이블 |
| 시황 | 없음 | 주요 8지표+뉴스 | 주요 8지표+뉴스 |
| 괴리 체크 | 없음 | yellow/red 만 | 전 항목 |
| 리스크 판정 | 없음 | 없음 | 풀 (12 스텝) |
| 액션 제안 | 없음 | 없음 | What-If 포함 |
| 스크리닝 | 없음 | 없음 | 조건부 Top3 |
| 리뷰 | 없음 | 없음 | 자동 리뷰 |

#### 데이터 저장

결과는 `data/session_logs/routine/` 에 자동 저장한다:
- `daily_YYYYMMDD.json` / `weekly_YYYYMMDD.json`

### Conviction 위반 감지 (KIK-729)

Strategist 출력 후, 오케스트레이터 자신이 다음을 자동 실행한다:

1. `notes.load_notes(note_type="thesis")` 로 conviction 종목 리스트를 취득
   - thesis 의 content 에 "홀드확정", "안 팜", "매도금지", "conviction" 을 포함 or `source` 가 `user-conviction*` 으로 시작하는 것
2. Strategist 출력 텍스트에서 매도 제안 종목을 추출 (매도/처분/철수/손절/비중축소 키워드 주변의 종목 티커)
3. 매도 제안 리스트와 conviction 종목이 교차하면 `context: conviction_violation` 을 세트
4. `auto_review.trigger.context: conviction_violation` 이 매치 → Reviewer 를 강제 기동

**중요**: conviction 위반 감지는 의식 기반이 아니라 장치로 강제한다. orchestrator 는 서브에이전트 완료 후 반드시 이 체크를 실행한다.

### Thesis Check (KIK-715)

HC / Strategist 완료 후, PF 종목의 thesis 참조를 기계적으로 검증한다. orchestration.yaml 의 `thesis_check` 로 정의되며, auto_review 보다 먼저 실행된다.

1. `load_notes(note_type="thesis")` 로 전 PF 종목의 thesis 를 취득
2. thesis 가 있는 종목인데 출력에 thesis 참조가 없음 → ⚠️ "thesis 미참조" 를 사용자에게 통지
3. thesis 미등록 종목이 있음 → ⚠️ "테제 미등록: [종목명]" 을 통지
4. PF 밖의 단발 분석 시에는 스킵 (`skip_condition: no_portfolio_context`)

### History Check (KIK-740)

투자 판단 (매도/매수/교체/리밸런싱/손절/익절 등) 을 포함하는 종목 분석 시, **4LLM 병렬로 과거의 역사적 유사 사례를 자동 체크** 한다. LLM 내장 지식+Web 검색을 활용하며, 라이브러리 축적은 하지 않는다.

#### 발동 조건 (자동)

다음 중 하나에 해당 → history_check 자동 발동:

1. `routing.yaml` 의 해당 패턴에 `history_check: true` 플래그가 있음
2. 사용자 입력에 투자 판단 키워드가 포함됨:
   - 매도 / 손절 / 익절 / 처분 / 철수
   - 매수 / 추가매수 / 신규 진입
   - 교체 / 리밸런싱 / 개선 / 조정
   - "역사" "과거" "사례" "패턴" (명시 요청)

#### 발동하지 않는 경우 (중요)

- 단순 정보 조회 ("PER 얼마?", "VIX 확인", "삼성전자 어때?" 등)
- 아침 요약 / `mode: routine-*` (노이즈 회피)
- 단독 health-checker / risk-assessor 실행
- conviction 종목에 대한 "보유 확인" 수준의 문의

#### 4LLM 병렬의 역할 분담

오케스트레이터가 API 키가 설정된 LLM 만 병렬 기동한다 (graceful degradation).

| LLM | 역할 | 담당 영역 | 호출 |
|:---|:---|:---|:---|
| **Claude (자신)** | Portfolio Aligner | PF 정합·통합 판단·사용자 이력 대조 | 오케스트레이터 층에서 직접 실행 |
| **GPT** (`gpt-5.5`, reasoning='high') | Devil's Advocate | 반증·실패 사례 지적 | `call_llm('gpt', ...)` |
| **Gemini** (`gemini-3-flash-preview`, web_search=True) | Lesson Auditor | Google 검색으로 최신 사례 보완 | `call_llm('gemini', ..., web_search=True)` |
| **Grok** | Sentiment Analyst | X 시장의 유사 사례 반응 | `tools/grok.py` 의 `search_market()` or `call_llm('grok', ...)` |

**API 키 감지 로직**: `os.environ.get('OPENAI_API_KEY')`, `GEMINI_API_KEY`, `XAI_API_KEY` 가 미설정이면 해당 LLM 을 스킵. Claude (자신) 는 항상 동작.

**책임 소재**:
- API 키 감지는 오케스트레이터 층에서 수행 (각 LLM 호출 전에 판정)
- 미설정이어도 에러로 만들지 않고, 이용 가능한 LLM 만으로 실행 (graceful degradation)
- 이용 가능한 LLM 이 Claude (자신) 뿐이면 그 사실을 출력에 명기하고 내부 지식만으로 실행

**데이터 부족 시 폴백**:
- "실패 사례 ≥2건" "성공 사례 ≥1건" 의 최저 건수를 채우지 못하면 추측으로 보완하지 않고 "해당 사례 없음 (데이터 부족)" 을 명기
- 각 LLM 이 독립적으로 판정. 하나라도 기준 미달이면 통합 판단에 "데이터 부족" 플래그를 세운다

#### 공통 프롬프트 템플릿

```
종목: {symbol}
상황 요약: {context}
  실적: {earnings_summary}
  주가: {price_summary}
  펀더멘털: {fundamentals}
  관련 lesson: {lessons}
판단 테마: {decision_theme}
  예: 매도 검토 / 교체 검토 / 손절 판단

과거의 역사적 유사 사례를 다음 구조로 제시해 주세요:
- 성공 사례 (최소 1건): 같은 상황에서 회복한 기업, 그 요인
- 실패 사례 (최소 2건): 같은 상황에서 쇠퇴·파산한 기업, 그 요인
- 해당 종목과의 유사도 평가 (고/중/저) + 근거
- 반증 포인트 (맹신 회피를 위해 반드시 제시)
```

#### 결과 통합 (Claude 가 재정)

각 LLM 의 지적을 다음 구조로 분류:

```markdown
## 📚 역사적 유사 사례

### 전체 LLM 일치점
- ...

### 의견이 갈린 점 (불일치 하이라이트)
- Claude: ...
- GPT: ...
- Gemini: ...
- Grok: ...

### 통합 판단
- 최종 판단: ...
- 반증 패턴: ...
```

⚠️ MUST: **성공 사례만/실패 사례만 한쪽으로 치우친 제시는 금지**. 반드시 양론 병기.
⚠️ MUST: **반증 포인트를 반드시 포함한다** (맹신 회피).

#### 병렬 기동 패턴

오케스트레이터가 1개 메시지로 복수의 LLM 을 동시 호출:

```python
# 오케스트레이터 내 (의사 코드)
import asyncio  # 병렬은 Bash 로 복수의 python3 -c 를 동시 발화, 또는
# 개별 Bash run_in_background=True 로 병렬화

# 구현상은 Bash 의 run_in_background=True 를 3개 병렬 발화
Bash(call_llm gpt, run_in_background=True)
Bash(call_llm gemini, run_in_background=True)
Bash(grok search_market, run_in_background=True)
# Claude 자신은 내부 지식으로 동시에 사고
# 완료 후 통합
```

#### DeepThink 와의 차별화

| | history_check (KIK-740) | DeepThink |
|:---|:---|:---|
| 기동 | **자동** (투자 판단 키워드 감지) | 명시 트리거 |
| 라운드 수 | 1 | 복수 (수렴까지) |
| 소요 시간 | 30-60초 | 15-30분 |
| LLM 수 | 4 병렬 (1 라운드) | 4 병렬 + 반복 루프 |
| 용도 | 기존 판단에 역사 관점을 부가 | 전략 재설계·복잡한 시나리오 분기 |
| 비용 | $0.10/회 | $0.50-2.00/회 |

**규칙**: history_check 로 충분하면 DeepThink 를 쓰지 않는다. 복수의 불확실성이 얽힌 경우에만 DeepThink 로.

#### 이중 실행 방지

동일 세션에서 이미 history_check 가 실행됐으면 스킵한다.

### Reviewer 기동 방침 (KIK-659 / KIK-729 에서 재설계)

에이전트 실행 후, `orchestration.yaml` 의 `auto_review` / `adhoc_review` 규칙에 따라 Reviewer 기동을 3분류로 제어한다.

#### 3분류

| 분류 | 대상 | 동작 |
|:---|:---|:---|
| 🔒 **자동** | 매매 확정 직전 / conviction 위반 감지 (위 "Conviction 위반 감지" 섹션 참조) / 주간 routine 의 strategist 출력 | 강제 실행 (사용자 확인 불필요) |
| 🔍 **애드혹** | 단발 strategist / screener 단독 / `review: true` 플래그 / 출력에 투자 판단 키워드 (매도/매수/교체/리밸런싱 등) | Layer 4 말미에 "🔍 Reviewer 로 체크할까요? [y/skip]" 을 출력. **다음 턴** 에서 사용자가 `y`/`yes`/`리뷰해줘` 등을 입력하면 Reviewer 기동. 그 외 입력은 확정 (다음 의도로 처리) |
| ⏭ **스킵** | health-checker / researcher / analyst / risk-assessor 의 단독 실행 (연쇄 없음) | 아무것도 내지 않는다 |

**`agent_includes` 의 시맨틱**: `agents` 배열 (연쇄·병렬 포함) 에 대상 에이전트가 **포함되어 있으면** 매치. 예를 들어 `agents: [health-checker, strategist]` 연쇄는 `agent_includes: strategist` 에 매치해 adhoc_review 가 발동한다. `agent_only` 는 배열 길이 == 1 이고 그 에이전트뿐인 경우에 매치 (skip_review 에서 사용).

#### 애드혹 기동 시 UX

```
🔍 Reviewer 실행 중...
  ├─ Risk (GPT)    ⏳
  ├─ Logic (Gemini) ⏳
  └─ Data (Claude)  ⏳
```

**결과 포맷**:
- ✅ PASS → "3관점 LGTM" 1줄만
- ⚠️ WARN → 관점별 1줄 + 해당 부분 인용 + "무시/반영" 선택
- ❌ FAIL → FAIL 이유 + 수정 방침안 + 승인 대기 (기존 `retry_on_fail` 답습)

**이중 실행 방지**: 동일 세션에서 이미 Reviewer 가 실행됐으면 스킵한다.

### Reviewer 기동 시 lesson 주입

Reviewer 를 기동하기 전에 `tools/notes.py` 의 `load_notes(note_type="lesson")` 으로 로컬 lesson 을 취득해 prompt 에 포함한다.
get_context() 가 Neo4j 미접속으로 None 을 반환해도 lesson 은 data/notes/ 에서 직접 읽을 수 있으므로 확실히 리뷰에 반영된다.

```
# Reviewer 의 prompt 에 넘기는 정보
1. agent.md + examples.yaml 의 내용
2. 리뷰 대상 (전단 에이전트의 출력 전문)
3. 사용자의 입력 (원래 의도)
4. 과거 lesson 일람 (load_notes(note_type="lesson") 으로 취득)
```

## Direct Actions (기록계 조작)

routing.yaml 에서 `action: direct` 로 분류되는 조작은 에이전트가 필요 없다. 오케스트레이터가 직접 실행한다.

### 쓰기

| 조작 | 툴 | 데이터 저장처 |
|:---|:---|:---|
| 투자 메모 저장 (thesis/concern/lesson/observation/review/target/journal) | `tools/graphrag.py` merge_note | CSV(master) + Neo4j(view) |
| 관심종목 추가·삭제 | CSV 직접 읽기/쓰기 | CSV(master) + Neo4j(view) |
| 매매 기록 (buy/sell, 1주 단위) | `tools/graphrag.py` merge_trade | CSV(master) + Neo4j(view) |
| 현금 잔고 업데이트 (`total_krw`, KRW/USD breakdown) | JSON 직접 읽기/쓰기 | data/cash_balance.json |

판단이 필요 없는 데이터 조작이므로 에이전트는 기동하지 않는다.

### 읽기 (각 에이전트가 GraphRAG 경유로 취득)

| 데이터 | 읽는 에이전트 | 활용 방법 |
|:---|:---|:---|
| 투자 메모 | Analyst, Strategist | 과거 분석·테제와의 비교 |
| lesson | Strategist, Reviewer | 판단 전 제약 조건, 바이어스 보정 |
| 관심종목 | Screener | 후보와 중복 체크 |
| 매매 기록 | Health Checker, Analyst | PF 진단, 보유자 관점의 분석 |
| 현금 잔고 | Health Checker, Strategist | PF 전체상 파악, 매수 예산 참조 |

### 데이터 동기화 (KIK-676/677)

"sync 해줘", "데이터 동기화해줘", "정합성 체크" 로 로컬→GraphRAG 의 차분 감지·동기화를 실행한다.

**동기화 흐름**:
1. `data/sync_status.yaml` 의 last_sync 를 확인
2. last_sync 보다 새로운 파일을 차분으로 감지
3. 차분 테이블을 사용자에게 제시
4. 사용자 확인 후, 로컬 → GraphRAG 방향으로 동기화 실행
5. `data/sync_status.yaml` 을 갱신

**동기화 대상**:

| data/ | GraphRAG 노드 | 동기화 함수 |
|:---|:---|:---|
| data/notes/*.json | Note | merge_note() |
| data/history/screen/*.json | Screen + SURFACED | merge_screen() |
| data/history/trade/*.json | Trade + BOUGHT/SOLD | merge_trade() |
| data/history/report/*.json | Report + ANALYZED | merge_report() |
| data/history/research/*.json | Research | merge_note() |
| data/history/health/*.json | HealthCheck | merge_note() |
| data/portfolio.csv | Portfolio + HOLDS | sync_portfolio() |
| data/cash_balance.json | MarketContext (cash) | merge_note(type=cash) |

**동기화 방향은 항상 로컬 → GraphRAG** (단방향).
**중복 방지**: graph_store 의 전 함수가 MERGE 를 사용. 같은 id 는 덮어써지며 이중 등록되지 않는다.

**벡터 임베딩 생성**: sync 시 TEI (`src/data/embedding_client.py`) 가 이용 가능하면 각 데이터의 semantic_summary 에서 벡터 임베딩을 생성해 GraphRAG 노드에 부여한다. 이로써 "전에 조사한 반도체 관련" 같은 모호한 벡터 검색이 가능해진다. TEI 미기동 시에는 임베딩 없이 동기화한다 (graceful degradation).

### 데이터 저장 원칙

- 마스터: data/ (JSON/CSV) — **항상 저장. GraphRAG 유무와 무관**
- 뷰: GraphRAG / Neo4j (dual-write, 접속 시에만)
- GraphRAG 가 없어도 동작한다 (graceful degradation)

## Orchestration (자율 수정 루프)

`orchestration.yaml` 에 따라 에이전트 실행 후의 자동 리트라이·에스컬레이션을 제어한다.

- 스크리닝 0건 → 조건 완화해 자율 리트라이 (최대 2회)
- Reviewer PASS/WARN → 그대로 출력 (자율)
- **Reviewer FAIL → FAIL 이유와 수정 방침안을 사용자에게 제시 → 승인 후 리트라이** (최대 2회)
- 재시도 상한 도달 → 현시점 결과를 그대로 제시

## Post-Action

### 1. 결과를 사용자에게 제시

에이전트의 출력을 사용자에게 제시한다. Reviewer 의 자동 삽입은 `orchestration.yaml` 의 `auto_review` 로 제어.

### 2. 데이터 저장 (자율 실행) (KIK-674)

에이전트 실행 후, 결과를 아래에 저장한다. **사용자의 지시를 기다리지 않고 자율적으로 실행한다.**

| 에이전트 | data/ 로컬 저장 |
|:---|:---|
| Screener | data/screening_results/{preset}_{date}.json |
| Analyst | data/reports/{symbol}_{date}.json |
| Researcher | data/research/{topic}_{date}.json |
| Health Checker | data/session_logs/{date}.json |
| Strategist | data/session_logs/{date}.json |
| Reviewer | data/reviews/{date}.json |

**데이터 저장 원칙**:
- **data/ (JSON/CSV) 는 항상 저장한다.** 이것이 유일한 자동 저장처
- **GraphRAG 쓰기는 자동 실행하지 않는다.** 사용자가 "sync 해줘" 라고 지시한 경우에만 실행한다
- **저장의 최종 책임은 오케스트레이터가 진다.** 서브에이전트가 "저장 완료" 라고 보고해도 오케스트레이터는 반드시 스스로 파일 존재를 확인 (ls or read) 하고, 없으면 직접 저장한다. 서브에이전트의 보고를 그대로 믿지 않는다 (저장 처리가 실패했을 가능성이 있다)

**저장 상태 표시**:

데이터 저장 후, 다음 상태를 사용자에게 반드시 표시한다:

```
💾 data/screening_results/trending_kr_20260420.json
```

**sync 제안 (Neo4j 접속 시에만)**:

데이터 저장 후, Neo4j 가 접속 중이면 "sync 할까요?" 라고 사용자에게 확인한다.
Neo4j 미접속 시에는 제안하지 않는다 (graceful degradation).

```python
# Neo4j 접속 판정
from src.data.graph_store._common import is_available
if is_available():
    # → "💾 저장했습니다. sync 할까요?" 라고 제안
```

사용자가 승인한 경우에만 아래 "3. 데이터 동기화" 를 실행한다.

### 3. 데이터 동기화 (sync)

사용자가 "sync 해줘", "GraphRAG 와 동기화" 라고 지시했거나, 위 sync 제안을 사용자가 승인한 경우, data/ → GraphRAG 단방향 동기화를 실행한다.

**sync 대상**:

| data/ | GraphRAG 노드 | 동기화 함수 |
|:---|:---|:---|
| data/notes/*.json | Note | merge_note() |
| data/history/screen/*.json | Screen + SURFACED | merge_screen() |
| data/history/trade/*.json | Trade + BOUGHT/SOLD | merge_trade() |
| data/history/report/*.json | Report + ANALYZED | merge_report() |
| data/history/research/*.json | Research | merge_note() |
| data/history/health/*.json | HealthCheck | merge_note() |
| data/portfolio.csv | Portfolio + HOLDS | sync_portfolio() |

**sync 상태 관리**: `data/sync_status.yaml` 로 최종 동기화 일시와 동기화 완료 파일 일람을 관리. 파일 갱신 일시가 last_sync 보다 새로우면 미동기화로 판정.

**중복 방지**: graph_store 의 전 함수가 Neo4j 의 MERGE 를 사용. 같은 id 의 데이터는 덮어써지므로 첫 full sync 에서도 이중 등록되지 않는다.

### 4. 배운 점 기록 제안

에이전트 실행 후, 결과에 배움·교훈·깨달음이 있다고 판단되면 사용자에게 "기록할까요?" 라고 제안한다.

**제안 조건** (하나라도 해당):
- Reviewer 가 WARN/FAIL 을 냈다 (실패 패턴의 기록 가치 있음)
- 과거 lesson 과 모순되는 결과가 나왔다
- 사용자가 의외의 반응을 했다 (예상 밖의 판단·확신)
- 스크리닝에서 새로운 테마·관점이 나왔다

**제안 포맷**:
```
📝 배운 점을 기록할까요?
예: "방산주는 지정학 이벤트에서 반드시 오르는 것은 아니다"
```

**저장 흐름**:
1. 사용자가 승인 → `tools/notes.py` 의 `save_note(note_type="lesson")` 으로 `data/notes/` 에 저장
2. Neo4j 접속 중 → 저장 후 그대로 GraphRAG 에도 sync (`merge_note()`)
3. Neo4j 미접속 → data/ 에만 저장 (다음 sync 시 반영)

**기록하지 않는 경우**: 사용자가 불필요하다고 판단하면 스킵. 강제하지 않는다.

### 5. 다음 액션 제안

- 다음의 자연스러운 액션을 1-2개 제안한다
- 직전 대화에서 다룬 종목·결과를 이어받아 생략된 정보를 보완한다

## Layer 5: Cited Sources (KIK-739)

"**무엇에 근거해 결론을 냈는가**" 를 가시화함으로써 오래된 정보가 쓰레기로 변하는 것을 막는다.
2026-04-28 세션 (META 추천 실수·AVGO/NEE ATH 간과) 의 근본 대책.

### 적용 조건 (Layer 5 를 내야 하는 패턴)

- 투자 판단 / 매매 제안 / 트림 / 리밸런싱을 포함
- DeepThink Step 5 출력
- Strategist agent 의 최종 제안
- routine-weekly 리포트
- `routing.yaml` 의 해당 routing 에 `layer5: required` 플래그가 있는 경우

반대로 **불필요한 경우**: `health-checker` 단독 / `risk-assessor` 단독 / 단순 사실 조회
(Pattern A 경량) 는 Layer 5 를 스킵해도 된다.

### 출력 포맷

`src/data/citation_formatter.format_cited_sources(cited_lessons, cited_theses, used_for_map)` 가
markdown 블록을 반환한다. 본문 말미에 추가하기만 하면 된다.

```
## 📚 Cited Sources

### Lessons
- 🟢 [permanent] 2026-04-24 PF 밸런스 normal — Cash 15-20% 판정
- 🟢 [permanent] 2026-04-25 035420.KS HOLD-LOCK — 매도 대상 제외
- 🟡 [seasonal/45일] 2026-03-22 미국 금리 4% 초과 헤지 — 금리 민감도·USD/KRW 판정 ⚠ 오래됨: 환경 변화 있으면 재확인

### Theses
- 🔒 [conviction] 2026-04-25 035420.KS 홀드 확정
- 🟢 2026-04-24 MSFT 투자 테제 — 눌림목 추가 매수 근거
```

### 신선도 마커 규칙

| 마커 | 조건 |
|:---:|:---|
| 🟢 | `permanent` 태그 / 30일 이내 |
| 🟡 | `seasonal` 태그로 31-90일 |
| 🔴 | `seasonal` 태그로 91일 초과 / date 불명 |
| ⛔ | `expired` 태그 → 자동 제외 (출력하지 않음) |
| 🔒 | thesis with `conviction_override=true` |

### 인용 판정 (citation 추출)

DeepThink Step 5 에서 `verify_lesson_cited()` (KIK-738) 가 성공한 리스트에서 자동 추출:

```python
cited_lessons = [l for l in relevant_lessons if l.get("id") not in missing_lesson_ids]
```

verify 가 abort 한 시점에 citation 이 1건도 없는 상태는 발생하지 않는다 (lesson 형해화 저지).

## References

- 라우팅 few-shot: [routing.yaml](./routing.yaml)
- 자율 수정 루프: [orchestration.yaml](./orchestration.yaml)
- Citation formatter: [src/data/citation_formatter.py](../../../src/data/citation_formatter.py)
