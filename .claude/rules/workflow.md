# 개발 워크플로우 규칙

> 코딩 규약·의존성·테스트 인프라는 [development.md](development.md) 참조.

## 원칙

- 모든 개발 작업은 **Worktree 위에서 수행**한다（main 브랜치 직접 편집 금지）
- 각 issue 는 **설계→구현→단위 테스트→코드 리뷰→통합 시험** 의 5단계로 진행한다
- 통합 시험은 **Teams（에이전트 팀）** 를 구성해 병렬로 수행한다

## 1. Worktree 생성

**권장**: 헬퍼 스크립트로 일괄 셋업（KIK-745）

```bash
bash scripts/setup_worktree.sh KIK-NNN [short-desc]
# → worktree 생성 + sample fixture 복사 (개인 PF 는 건드리지 않음)
# → ~/stock-skills-kik{NNN} 에 전개, 즉시 pytest 실행 가능
```

수동으로 할 경우:

```bash
git worktree add -b feature/kik-{NNN}-{short-desc} ~/stock-skills-kik{NNN} main
mkdir -p ~/stock-skills-kik{NNN}/data
cp tests/fixtures/sample_portfolio.csv ~/stock-skills-kik{NNN}/data/portfolio.csv
cp tests/fixtures/sample_cash_balance.json ~/stock-skills-kik{NNN}/data/cash_balance.json
```

- 작업 디렉터리: `~/stock-skills-kik{NNN}`
- 브랜치명: `feature/kik-{NNN}-{short-desc}`
- 이후 모든 작업（구현·테스트·통합 시험）은 이 worktree 위에서 수행한다

### Worktree 위의 준비（KIK-745 에서 갱신）

⚠️ **개인 PF（`~/stock-skills/data/portfolio.csv` 등）를 `cp` 로 worktree 에
복사하는 것은 금지**. 실수로 `git add -f` 한 경우 개인 종목·실제 수량이
공개 저장소로 유출되기 때문이다.

대신 아래 중 하나를 사용한다:

1. `tests/fixtures/sample_portfolio.csv` 의 범용 테스트 종목（권장）
2. 환경 변수로 개인 PF 를 **읽기 전용 참조**:
   ```bash
   export STOCK_SKILLS_DATA_DIR=$HOME/stock-skills/data
   # tools/portfolio_io.py 의 csv_path 인자에 전달
   ```

## 2. 설계 단계

- `EnterPlanMode` 로 코드베이스를 조사하고 구현 방침을 세운다
- 영향 범위·변경 파일·테스트 방침을 명확히 한다
- 사용자 승인을 얻은 뒤 구현으로 넘어간다

## 3. 구현 단계

- Worktree 위에서 코드를 변경한다
- PostToolUse hook 에 의해 `.py` 파일 편집 시 자동으로 `pytest tests/ -q` 가 실행된다
- 전체 테스트 PASS 를 유지하면서 구현을 진행한다

## 4. 단위 테스트

- 신규 모듈에는 대응하는 테스트 파일을 만든다
- `python3 -m pytest tests/ -q` 로 전체 PASS 를 확인한다
- Worktree 위에서 실행: `cd ~/stock-skills-kik{NNN} && python3 -m pytest tests/ -q`

## 5. 코드 리뷰（Teams）

단위 테스트 PASS 후, **리뷰 팀을 구성해 변경 내용을 다각도로 검증**한다.

### 팀 구성

| 리뷰어명 | 관점 | 체크 내용 |
|-------------|------|-------------|
| arch-reviewer | 설계·구조 | 모듈 분할, 책임 분리, 기존 패턴과의 정합성, 순환 의존 유무 |
| logic-reviewer | 로직·정확성 | 계산 로직의 올바름, 엣지 케이스, 에러 핸들링, 이상값 가드 누락 |
| test-reviewer | 테스트 품질 | 테스트 커버리지, 경계값 테스트, 모킹의 적절성, 테스트 독립성 |

### 수행 절차

1. `TeamCreate` 로 팀 생성（예: `kik{NNN}-code-review`）
2. `TaskCreate` 로 각 리뷰어의 태스크 생성（대상 파일·변경 차분을 명시）
3. `Task` 로 3명의 리뷰어를 병렬 기동（`subagent_type=Explore`, Worktree 경로를 명시）
4. 각 리뷰어로부터 지적 수집
5. 지적이 있으면 수정 → 단위 테스트 재실행 → 재리뷰（필요 시）
6. 전체 리뷰어 LGTM 이면 통합 시험으로 진행
7. 팀 종료·삭제

### 리뷰 대상 전달 방법

리뷰어에게는 아래 정보를 제공한다:

- Worktree 경로: `~/stock-skills-kik{NNN}`
- 변경 파일 목록: `git diff --name-only main` 결과
- 변경 차분: `git diff main` 개요
- 설계 의도: 설계 단계에서 정한 방침 요약

### 영향 범위에 따른 리뷰어 선정

변경이 소규모（1-2파일, 로직 변경 없음）인 경우 logic-reviewer 만으로 가능.
신규 모듈 추가나 대규모 리팩토링은 전체 리뷰어 필수.

## 6. 통합 시험（Teams）

구현 완료 후, **에이전트 팀을 구성해 각 스킬의 동작을 검증**한다.

### 팀 구성（표준）

| 테스터명 | 담당 | 검증 내용 |
|-----------|------|---------|
| screener-tester | 스크리닝 | Screener 에이전트를 여러 패턴으로 실행 |
| analyst-tester | 분석 | Analyst 에이전트로 종목 분석·ETF 평가 |
| portfolio-tester | 포트폴리오 | Health Checker + Strategist 로 PF 진단·추천 |
| researcher-tester | 리서치 | Researcher 에이전트로 뉴스·센티먼트 수집 |

### 수행 절차

1. `TeamCreate` 로 팀 생성（예: `kik{NNN}-integration-test`）
2. `TaskCreate` 로 각 테스터의 태스크 생성
3. `Task` 로 4명의 테스터를 병렬 기동（`team_name` 지정, Worktree 경로를 명시）
4. 전체 테스터 PASS 확인
5. 팀 종료·삭제

### 통합 시험 실행 방법

Worktree 위에서 에이전트를 자연어로 호출해 동작을 확인한다:

```
「한국 주식 밸류 종목 찾아줘」      → Screener 에이전트
「005930.KS 분석해 줘」            → Analyst 에이전트
「최신 뉴스 알려줘」               → Researcher 에이전트
「PF 괜찮아?」                    → Health Checker 에이전트
```

### 영향 범위에 따른 테스터 선정

변경이 특정 스킬에 한정되는 경우 관련 테스터만으로 통합 시험을 수행해도 된다.
단, 공통 모듈（`src/data/common.py`, `src/data/ticker_utils.py`）변경은 전체 테스터 필수.

## 7. 문서·규칙 갱신

**기능 구현 후, 머지 전에 반드시 아래를 확인·갱신한다.**

### 갱신 체크리스트

| 대상 | 갱신 조건 | 갱신 내용 |
|:---|:---|:---|
| 해당 `agent.md` + `examples.yaml` | 에이전트의 역할·툴이 바뀌었다 | 판단 프로세스, few-shot 예 |
| `routing.yaml` | 새로운 의도 패턴이 늘었다 | triggers, examples 추가 |
| `orchestration.yaml` | 재시도·리뷰 조건이 바뀌었다 | 규칙 추가 |
| `CLAUDE.md` | 아키텍처가 바뀌었다 | 구성도, 툴 목록 |
| `docs/data-models.md` | stock_info/stock_detail 필드가 바뀌었다 | 테이블 갱신 |
| `README.md` | 사용자용 기능 설명이 필요하다 | 사용법, 셋업 |

### 판단 기준

- **신기능 추가**: agent.md + examples.yaml + routing.yaml + README.md 갱신
- **기존 기능 개선**: 해당 agent.md + examples.yaml 만
- **버그 수정만**: 문서 갱신 불필요（단, 동작이 바뀌는 경우 agent.md 갱신）

## 8. 완료

```bash
# main 에 머지
cd ~/stock-skills
git merge --no-ff feature/kik-{NNN}-{short-desc}
git push

# Worktree 삭제
git worktree remove ~/stock-skills-kik{NNN}
git branch -d feature/kik-{NNN}-{short-desc}
```

- Linear issue 를 Done 으로 갱신한다
