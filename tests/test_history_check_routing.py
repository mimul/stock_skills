"""History Check 라우팅 플래그 테스트 (KIK-740)."""

from pathlib import Path

import yaml


ROUTING_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/routing.yaml"
SKILL_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/SKILL.md"
ORCHESTRATION_PATH = Path(__file__).resolve().parent.parent / ".claude/skills/stock-skills/orchestration.yaml"


def _load_routing():
    with ROUTING_PATH.open() as f:
        return yaml.safe_load(f)


def test_routing_yaml_loads():
    """routing.yaml 이 유효한 YAML 이고 examples 를 가진다."""
    data = _load_routing()
    assert "examples" in data
    assert isinstance(data["examples"], list)
    assert len(data["examples"]) > 0


def test_history_check_added_to_sell_decisions():
    """매도 판단 계열 (팔아야/손절/익절) 에 history_check: true 가 부여되어 있다."""
    data = _load_routing()
    sell_intents = ["이 종목 팔아야 해?", "손절해야 해?", "익절해야 해?"]
    found = {i: False for i in sell_intents}
    for ex in data["examples"]:
        if ex.get("intent") in sell_intents:
            assert ex.get("history_check") is True, f"history_check missing on {ex.get('intent')}"
            found[ex["intent"]] = True
    assert all(found.values()), f"Some sell-decision intents missing: {found}"


def test_history_check_added_to_replacement():
    """교체·PF 개선 계열에 history_check: true 가 부여되어 있다."""
    data = _load_routing()
    targets = ["교체 제안해줘", "PF 개선하고 싶어", "플랜 모드로", "리스크 확인하고 대체 종목 찾아줘"]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("history_check") is True, f"history_check missing on {ex.get('intent')}"
            found[ex["intent"]] = True
    assert all(found.values()), f"Some replacement intents missing: {found}"


def test_history_check_NOT_on_info_queries():
    """정보 조회 계열 (VIX/PF 확인/단순 분석) 에는 history_check 가 부여되지 않는다."""
    data = _load_routing()
    info_intents = ["VIX는?", "PF 괜찮아?", "삼성전자 어때?", "TODO 보여줘", "좋은 아침", "아침 요약"]
    for ex in data["examples"]:
        if ex.get("intent") in info_intents:
            assert ex.get("history_check") is not True, (
                f"history_check should NOT be on info query: {ex.get('intent')}"
            )


def test_history_check_NOT_on_routine():
    """routine-* mode 에는 history_check 가 부여되지 않는다."""
    data = _load_routing()
    for ex in data["examples"]:
        mode = ex.get("mode", "")
        if mode.startswith("routine-") or mode == "morning-summary":
            assert ex.get("history_check") is not True, (
                f"history_check should NOT be on routine: {ex.get('intent')}"
            )


def test_skill_md_documents_history_check():
    """SKILL.md 에 History Check 섹션이 존재한다."""
    text = SKILL_PATH.read_text()
    assert "### History Check" in text
    assert "KIK-740" in text
    assert "4LLM" in text or "4 LLM" in text


def test_skill_md_documents_graceful_degradation():
    """SKILL.md 에 graceful degradation 사양이 기재되어 있다."""
    text = SKILL_PATH.read_text()
    # API 키 미설정 시의 폴백 동작이 언급되어 있는가
    assert "graceful degradation" in text.lower() or "미설정" in text
    # 주요 API_KEY 명 중 하나가 포함된다
    assert any(k in text for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"])


def test_skill_md_documents_required_dual_view():
    """SKILL.md 에 "양론 병기 필수" "반증 필수" 규칙이 기재되어 있다."""
    text = SKILL_PATH.read_text()
    assert "양론 병기" in text
    assert "반증" in text


def test_skill_md_differentiates_from_deepthink():
    """SKILL.md 에 DeepThink 와의 차별화가 기재되어 있다."""
    text = SKILL_PATH.read_text()
    # History Check 섹션 안에서 DeepThink 와 비교되고 있다
    history_section_start = text.find("### History Check")
    history_section_end = text.find("### Reviewer 기동 방침", history_section_start)
    section = text[history_section_start:history_section_end]
    assert "DeepThink" in section
    # 기동 조건·라운드 수 등의 차별화 기재
    assert "자동" in section
    assert "라운드" in section or "복수" in section


def test_orchestration_yaml_has_history_check():
    """orchestration.yaml 에 history_check 자동 발동 정의가 있다."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    assert "history_check" in data
    hc = data["history_check"]
    # 필수 필드
    assert "trigger" in hc
    assert "llm_layout" in hc
    assert "skip_conditions" in hc
    assert "cost_guardrail" in hc


def test_orchestration_history_check_triggers():
    """history_check 의 trigger 에 투자 판단 키워드와 routing_flag 가 포함된다."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    triggers = data["history_check"]["trigger"]
    # routing_flag 트리거 존재
    flag_triggers = [t for t in triggers if "routing_flag" in t]
    assert len(flag_triggers) >= 1
    # keyword_detect 트리거 존재
    keyword_triggers = [t for t in triggers if "keyword_detect" in t]
    assert len(keyword_triggers) >= 1
    # 주요 키워드 (매도·손절·교체) 가 포함된다
    keywords = keyword_triggers[0]["keyword_detect"]
    for must in ["매도", "손절", "교체"]:
        assert must in keywords, f"keyword '{must}' missing"


def test_orchestration_history_check_llm_layout():
    """llm_layout 에 Claude (필수) + 옵션 3 LLM 이 정의되어 있다."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    layout = data["history_check"]["llm_layout"]
    llms = {item["llm"]: item for item in layout}
    # 4개의 LLM 이 정의되어 있다
    assert set(llms.keys()) == {"claude", "gpt", "gemini", "grok"}
    # Claude 는 required: true (필수)
    assert llms["claude"].get("required") is True
    # 옵션 3 LLM 에는 env_key 가 지정되어 있다
    for llm_name in ["gpt", "gemini", "grok"]:
        assert "env_key" in llms[llm_name]


def test_orchestration_history_check_skip_conditions():
    """routine_mode 와 morning_summary 에서 스킵하는 설정이 있다."""
    with ORCHESTRATION_PATH.open() as f:
        data = yaml.safe_load(f)
    skip = data["history_check"]["skip_conditions"]
    contexts = [s.get("context") for s in skip if "context" in s]
    assert "routine_mode" in contexts
    assert "morning_summary" in contexts
    assert "history_check_already_executed" in contexts


def test_skill_md_documents_data_insufficient_fallback():
    """SKILL.md 에 데이터 부족 시의 폴백 사양이 기재되어 있다."""
    text = SKILL_PATH.read_text()
    assert "데이터 부족" in text
    assert "해당 사례 없음" in text or "추측" in text
