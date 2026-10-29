"""session-start 자동 기동 hard gate 테스트 (KIK-741)."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTING_PATH = REPO_ROOT / ".claude/skills/stock-skills/routing.yaml"
SKILL_PATH = REPO_ROOT / ".claude/skills/stock-skills/SKILL.md"


def _load_routing():
    with ROUTING_PATH.open() as f:
        return yaml.safe_load(f)


def test_skill_description_mentions_session_start_keywords():
    """SKILL.md frontmatter description 에 session-start 키워드가 명기되어 있다."""
    text = SKILL_PATH.read_text()
    frontmatter_end = text.find("---", 3)
    frontmatter = text[:frontmatter_end]
    assert "description:" in frontmatter
    desc_line = [l for l in frontmatter.splitlines() if l.startswith("description:")][0]
    for keyword in ["좋은 아침", "아침", "현황", "PF"]:
        assert keyword in desc_line, f"keyword '{keyword}' missing from SKILL.md description"


def test_skill_description_mentions_reconcile_hard_gate():
    """SKILL.md frontmatter description 에 reconcile_session_state hard gate 언급."""
    text = SKILL_PATH.read_text()
    frontmatter_end = text.find("---", 3)
    frontmatter = text[:frontmatter_end]
    desc_line = [l for l in frontmatter.splitlines() if l.startswith("description:")][0]
    assert "reconcile_session_state" in desc_line or "hard gate" in desc_line


def test_routing_morning_summary_has_pf_state_required():
    """morning-summary mode 의 전 엔트리에 pf_state_required: true 가 있다."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "morning-summary":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 2, f"Expected ≥2 morning-summary entries, got {found}"


def test_routing_routine_daily_has_pf_state_required():
    """routine-daily mode 의 전 엔트리에 pf_state_required: true 가 있다."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "routine-daily":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 3, f"Expected ≥3 routine-daily entries, got {found}"


def test_routing_routine_weekly_has_pf_state_required():
    """routine-weekly mode 의 전 엔트리에 pf_state_required: true 가 있다."""
    data = _load_routing()
    found = []
    for ex in data["examples"]:
        if ex.get("mode") == "routine-weekly":
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found.append(ex["intent"])
    assert len(found) >= 3, f"Expected ≥3 routine-weekly entries, got {found}"


def test_routing_pf_health_check_has_pf_state_required():
    """PF / 헬스체크 / 스트레스 테스트 계열에 pf_state_required: true 가 있다."""
    data = _load_routing()
    targets = ["PF 괜찮아?", "스트레스 테스트 해줘"]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found[ex["intent"]] = True
    assert all(found.values()), f"Some PF/HC intents missing: {found}"


def test_routing_strategist_pf_decisions_have_pf_state_required():
    """투자 판단 계열 (교체/PF 개선/매도/손절/익절/플랜) 에 pf_state_required: true 가 있다."""
    data = _load_routing()
    targets = [
        "교체 제안해줘",
        "PF 개선하고 싶어",
        "플랜 모드로",
        "이 종목 팔아야 해?",
        "손절해야 해?",
        "익절해야 해?",
        "리스크 확인하고 대체 종목 찾아줘",
    ]
    found = {i: False for i in targets}
    for ex in data["examples"]:
        if ex.get("intent") in targets:
            assert ex.get("pf_state_required") is True, (
                f"pf_state_required missing on {ex.get('intent')}"
            )
            found[ex["intent"]] = True
    assert all(found.values()), f"Some strategist/PF-decision intents missing: {found}"


def test_routing_pf_state_NOT_on_pure_info_queries():
    """순수 정보 조회 (VIX/삼성전자 분석/최신 뉴스) 에는 pf_state_required 를 붙이지 않는다."""
    data = _load_routing()
    info_intents = ["VIX는?", "삼성전자 어때?", "최신 뉴스 알려줘", "반도체 업계 조사해줘"]
    for ex in data["examples"]:
        if ex.get("intent") in info_intents:
            assert ex.get("pf_state_required") is not True, (
                f"pf_state_required should NOT be on info query: {ex.get('intent')}"
            )


def test_routing_yaml_pf_state_field_documented_in_header_comment():
    """routing.yaml 의 머리말 주석에 pf_state_required 필드가 설명되어 있다."""
    text = ROUTING_PATH.read_text()
    header_end = text.find("agents:")
    header = text[:header_end]
    assert "pf_state_required" in header, "pf_state_required field not documented in header comment"
    assert "KIK-741" in header, "KIK-741 reference missing in header comment"


def test_skill_md_session_start_section_intact():
    """SKILL.md 의 Session Start State Reconcile 섹션이 남아 있다."""
    text = SKILL_PATH.read_text()
    assert "## Session Start State Reconcile" in text
    assert "reconcile_session_state" in text
    assert "pf_state_required" in text


def test_morning_intent_includes_extended_keywords():
    """확장 morning 키워드 (오늘 상황/현황 어때?) 가 등록되어 있다."""
    data = _load_routing()
    intents = [ex.get("intent") for ex in data["examples"]]
    assert "오늘 상황" in intents
    assert "현황 어때?" in intents
