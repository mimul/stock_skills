"""Lesson community classification and query (KIK-571).

Classifies lessons into thematic communities (판단편향/매매규칙/매크로전략)
using keyword-based rules. Provides Neo4j integration for
LessonCommunity nodes and CATEGORIZED_AS relationships.
"""

from typing import Optional

from src.data.lesson_conflict import tokenize


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# 커뮤니티별 분류 키워드 (한국어 + 영어). 토큰 일치 +2, 부분 문자열 일치 +1
_COMMUNITIES = {
    "판단편향": [
        "편향", "바이어스", "고정관념", "맹신", "기회손실", "과다", "금지",
        "신중", "낙관", "비관", "선입견", "과신",
        "패닉", "감정", "충동", "조급", "보수", "같은 날", "bias",
    ],
    "매매규칙": [
        "손절", "익절", "카탈리스트", "진입", "엔트리", "임계값",
        "rsi", "vix", "조건", "규칙", "룰", "타이밍", "매수",
        "매도", "스톱", "트레일", "포지션", "추가",
        "분할", "물타기", "중단", "정지", "거래량", "entry", "stop",
    ],
    "매크로전략": [
        "원유", "금리", "etf", "로테이션", "매크로",
        "인플레", "헤지", "환율", "원화 약세", "원화 강세", "원저", "원고",
        "채권", "일드", "섹터", "경기", "리세션", "침체",
        "fomc", "금리인상", "금리인하", "macro",
    ],
}


def classify_lesson(content: str = "", trigger: str = "") -> str:
    """Classify a lesson into a thematic community.

    Uses keyword matching on content + trigger text.
    Returns community name or "기타" if no clear match.
    """
    text = f"{trigger} {content}".lower()
    tokens = set(tokenize(text))

    scores: dict[str, int] = {}
    for community, keywords in _COMMUNITIES.items():
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            # Token match
            if kw_lower in tokens:
                score += 2
            # Substring match (for compound words)
            elif kw_lower in text:
                score += 1
        if score > 0:
            scores[community] = score

    if not scores:
        return "기타"

    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Neo4j operations
# ---------------------------------------------------------------------------

def merge_lesson_community(note_id: str, community_name: str) -> bool:
    """Create LessonCommunity node and CATEGORIZED_AS relationship."""
    try:
        from src.data.graph_store import _common
        if _common._get_mode() == "off":
            return False
        driver = _common._get_driver()
        if driver is None:
            return False
        with driver.session() as session:
            session.run(
                "MERGE (lc:LessonCommunity {name: $name})",
                name=community_name,
            )
            session.run(
                "MATCH (n:Note {id: $note_id}) "
                "MATCH (lc:LessonCommunity {name: $name}) "
                "MERGE (n)-[:CATEGORIZED_AS]->(lc)",
                note_id=note_id,
                name=community_name,
            )
        return True
    except Exception:
        return False


def get_lessons_by_theme(theme: str, limit: int = 5) -> list[dict]:
    """Get lessons belonging to a specific LessonCommunity.

    Returns list of {id, content, trigger, expected_action, date, symbol}.
    """
    try:
        from src.data.graph_query._common import _get_driver
        driver = _get_driver()
        if driver is None:
            return []
        with driver.session() as session:
            result = session.run(
                "MATCH (n:Note {type: 'lesson'})-[:CATEGORIZED_AS]->"
                "(lc:LessonCommunity {name: $theme}) "
                "RETURN n.id AS id, n.content AS content, "
                "n.trigger AS trigger, n.expected_action AS expected_action, "
                "n.date AS date "
                "ORDER BY n.date DESC LIMIT $limit",
                theme=theme,
                limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


def get_all_lesson_communities() -> list[dict]:
    """Get all LessonCommunity nodes with their lesson counts.

    Returns list of {name, count}.
    """
    try:
        from src.data.graph_query._common import _get_driver
        driver = _get_driver()
        if driver is None:
            return []
        with driver.session() as session:
            result = session.run(
                "MATCH (lc:LessonCommunity) "
                "OPTIONAL MATCH (n:Note)-[:CATEGORIZED_AS]->(lc) "
                "RETURN lc.name AS name, count(n) AS count "
                "ORDER BY count DESC"
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Intent → theme mapping (for KIK-569 integration)
# ---------------------------------------------------------------------------

# 사용자 의도 키워드 → LessonCommunity 매핑 (한국어 + 영어)
_INTENT_THEME_MAP = {
    "매매": "매매규칙",
    "손절": "매매규칙",
    "익절": "매매규칙",
    "매수": "매매규칙",
    "매도": "매매규칙",
    "진입": "매매규칙",
    "포지션": "매매규칙",
    "헬스체크": "매매규칙",
    "health": "매매규칙",
    "adjust": "매매규칙",
    "시황": "매크로전략",
    "매크로": "매크로전략",
    "금리": "매크로전략",
    "vix": "매크로전략",
    "환율": "매크로전략",
    "장세": "매크로전략",
    "증시": "매크로전략",
    "편향": "판단편향",
    "바이어스": "판단편향",
    "판단": "판단편향",
    "분석": "판단편향",
}


def infer_theme_from_input(user_input: str) -> Optional[str]:
    """Infer the most relevant LessonCommunity from user input."""
    if not user_input:
        return None
    text = user_input.lower()
    tokens = set(tokenize(text))
    scores: dict[str, int] = {}
    for keyword, theme in _INTENT_THEME_MAP.items():
        if keyword.lower() in tokens or keyword.lower() in text:
            scores[theme] = scores.get(theme, 0) + 1
    if not scores:
        return None
    return max(scores, key=scores.get)
