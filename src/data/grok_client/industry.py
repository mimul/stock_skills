"""업종 관련 Grok API 함수: search_industry.

KIK-508 서브모듈 분할 시 grok_client.py 에서 추출.
"""

from src.data.grok_client._common import (
    EMPTY_INDUSTRY,
    _call_grok_api,
    _contains_korean,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------

def _build_industry_prompt(industry_or_theme: str, context: str = "") -> str:
    """업종 리서치용 프롬프트를 만든다.

    업종/테마명에 한글이 있으면 한국어 프롬프트, 그 외는 영어 프롬프트.
    """
    context_block = f"{context}\n\n" if context else ""
    if _contains_korean(industry_or_theme):
        return (
            f"{context_block}"
            f"'{industry_or_theme}' 업종·테마에 대해 X(Twitter)와 웹의 최신 정보를 바탕으로 다음을 조사해 주세요.\n\n"
            f"1. 업종 현황과 최근 트렌드\n"
            f"2. 주요 플레이어와 주목 기업\n"
            f"3. 성장 동력과 리스크 요인\n"
            f"4. 규제·정책 동향\n"
            f"5. 투자자 주목 포인트\n\n"
            f"JSON 형식으로 답변:\n"
            f'{{\n'
            f'  "trends": ["트렌드1", "트렌드2"],\n'
            f'  "key_players": [\n'
            f'    {{"name": "기업명", "ticker": "심볼", "note": "주목 이유"}}\n'
            f'  ],\n'
            f'  "growth_drivers": ["동력1", "동력2"],\n'
            f'  "risks": ["리스크1", "리스크2"],\n'
            f'  "regulatory": ["규제 동향1", "규제 동향2"],\n'
            f'  "investor_focus": ["주목점1", "주목점2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Research the \"{industry_or_theme}\" industry/theme using X (Twitter) and web sources. Provide:\n\n"
        f"1. Current trends\n"
        f"2. Key players and notable companies\n"
        f"3. Growth drivers and risk factors\n"
        f"4. Regulatory/policy developments\n"
        f"5. Investor focus points\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "trends": ["trend1", "trend2"],\n'
        f'  "key_players": [\n'
        f'    {{"name": "company", "ticker": "SYMBOL", "note": "reason"}}\n'
        f'  ],\n'
        f'  "growth_drivers": ["driver1", "driver2"],\n'
        f'  "risks": ["risk1", "risk2"],\n'
        f'  "regulatory": ["development1", "development2"],\n'
        f'  "investor_focus": ["point1", "point2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# 공개 검색 함수
# ---------------------------------------------------------------------------

def search_industry(
    industry_or_theme: str,
    timeout: int = 30,
    context: str = "",
) -> dict:
    """X·웹 검색으로 업종 또는 테마를 조사한다.

    Parameters
    ----------
    industry_or_theme : str
        업종명 또는 테마 (예: "반도체", "EV", "AI").
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        스키마는 EMPTY_INDUSTRY 참조.
    """
    raw_text = _call_grok_api(_build_industry_prompt(industry_or_theme, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_INDUSTRY)

    result = dict(EMPTY_INDUSTRY)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("trends"), list):
        result["trends"] = parsed["trends"]
    if isinstance(parsed.get("key_players"), list):
        result["key_players"] = parsed["key_players"]
    if isinstance(parsed.get("growth_drivers"), list):
        result["growth_drivers"] = parsed["growth_drivers"]
    if isinstance(parsed.get("risks"), list):
        result["risks"] = parsed["risks"]
    if isinstance(parsed.get("regulatory"), list):
        result["regulatory"] = parsed["regulatory"]
    if isinstance(parsed.get("investor_focus"), list):
        result["investor_focus"] = parsed["investor_focus"]

    return result
