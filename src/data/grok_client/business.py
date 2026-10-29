"""비즈니스 모델 분석 Grok API 함수: search_business, synthesize_text.

KIK-508 서브모듈 분할 시 grok_client.py 에서 추출.
"""

from src.data.grok_client._common import (
    EMPTY_BUSINESS,
    _call_grok_api,
    _get_api_key,
    _is_korean_stock,
    _contains_korean,
    _parse_json_response,
    reset_error_state,
)


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------

def _build_business_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """비즈니스 모델 분석용 프롬프트를 만든다.

    한국 종목(.KS/.KQ)이거나 회사명에 한글이 있으면 한국어 프롬프트,
    그 외는 영어 프롬프트를 사용한다. JSON 키는 동일하다.
    """
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    if _is_korean_stock(symbol) or _contains_korean(company_name):
        return (
            f"{context_block}"
            f"{symbol}{name_part} 의 비즈니스 모델을 웹과 X(Twitter) 정보를 바탕으로 자세히 분석해 주세요.\n\n"
            f"1. 사업 개요(무엇으로 돈을 버는가)\n"
            f"2. 사업 부문 구성(부문명, 매출 비중, 개요)\n"
            f"3. 수익 모델(스톡형/플로우형/구독/라이선스 등)\n"
            f"4. 경쟁 우위(진입장벽, 브랜드, 기술, 네트워크 효과 등)\n"
            f"5. 핵심 KPI(투자자가 주목해야 할 지표)\n"
            f"6. 성장 전략(중기 경영계획, M&A, 신사업 등)\n"
            f"7. 사업 리스크(구조적 리스크, 의존도 등)\n\n"
            f"JSON 형식으로 답변:\n"
            f'{{\n'
            f'  "overview": "사업 개요 텍스트",\n'
            f'  "segments": [\n'
            f'    {{"name": "부문명", "revenue_share": "매출 비중(예: 40%)", "description": "개요"}}\n'
            f'  ],\n'
            f'  "revenue_model": "수익 모델 설명",\n'
            f'  "competitive_advantages": ["우위1", "우위2"],\n'
            f'  "key_metrics": ["KPI1", "KPI2"],\n'
            f'  "growth_strategy": ["전략1", "전략2"],\n'
            f'  "risks": ["리스크1", "리스크2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Analyze the business model of {symbol}{name_part} using web and X (Twitter) sources. Provide:\n\n"
        f"1. Business overview (how the company makes money)\n"
        f"2. Business segments (name, revenue share, description)\n"
        f"3. Revenue model (recurring/transactional/subscription/licensing etc.)\n"
        f"4. Competitive advantages (moats, barriers to entry, brand, technology)\n"
        f"5. Key metrics (KPIs investors should watch)\n"
        f"6. Growth strategy (M&A, new markets, product roadmap)\n"
        f"7. Business risks (structural risks, dependencies)\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "overview": "business overview text",\n'
        f'  "segments": [\n'
        f'    {{"name": "Segment Name", "revenue_share": "e.g. 40%", "description": "overview"}}\n'
        f'  ],\n'
        f'  "revenue_model": "description of revenue model",\n'
        f'  "competitive_advantages": ["advantage1", "advantage2"],\n'
        f'  "key_metrics": ["KPI1", "KPI2"],\n'
        f'  "growth_strategy": ["strategy1", "strategy2"],\n'
        f'  "risks": ["risk1", "risk2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# 공개 검색 함수
# ---------------------------------------------------------------------------

def synthesize_text(prompt: str, timeout: int = 20) -> str:
    """Grok API 순수 텍스트 합성(검색 툴 없음). KIK-452.

    지식 그래프의 컨텍스트 데이터를 요약할 때 사용한다.
    _call_grok_api 에 use_tools=False 로 위임한다.
    보조 호출이므로 _error_state 를 갱신하지 않는다 — _call_grok_api 가
    바꾼 상태를 반환 전에 초기화한다.

    Parameters
    ----------
    prompt : str
        합성 프롬프트(한국어 또는 영어).
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    str
        생성 텍스트. 사용 불가/오류 시 "".
    """
    if not _get_api_key():
        return ""
    try:
        result = _call_grok_api(prompt, timeout=timeout, use_tools=False)
        # 보조 호출이므로 다른 호출자가 쓰는 메인 에러 상태에 영향을 주지 않도록 초기화
        reset_error_state()
        return result
    except Exception:
        return ""


def search_business(
    symbol: str,
    company_name: str = "",
    timeout: int = 60,
    context: str = "",
) -> dict:
    """X·웹 검색으로 기업의 비즈니스 모델을 조사한다.

    Parameters
    ----------
    symbol : str
        티커 (예: "035420.KS", "AAPL").
    company_name : str
        프롬프트 정확도를 높이기 위한 회사명.
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        스키마는 EMPTY_BUSINESS 참조.
    """
    raw_text = _call_grok_api(_build_business_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_BUSINESS)

    result = dict(EMPTY_BUSINESS)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("overview"), str):
        result["overview"] = parsed["overview"]

    segments = parsed.get("segments")
    if isinstance(segments, list):
        validated = []
        for seg in segments:
            if isinstance(seg, dict):
                validated.append({
                    "name": seg.get("name", "") if isinstance(seg.get("name"), str) else "",
                    "revenue_share": seg.get("revenue_share", "") if isinstance(seg.get("revenue_share"), str) else "",
                    "description": seg.get("description", "") if isinstance(seg.get("description"), str) else "",
                })
        result["segments"] = validated

    if isinstance(parsed.get("revenue_model"), str):
        result["revenue_model"] = parsed["revenue_model"]
    if isinstance(parsed.get("competitive_advantages"), list):
        result["competitive_advantages"] = parsed["competitive_advantages"]
    if isinstance(parsed.get("key_metrics"), list):
        result["key_metrics"] = parsed["key_metrics"]
    if isinstance(parsed.get("growth_strategy"), list):
        result["growth_strategy"] = parsed["growth_strategy"]
    if isinstance(parsed.get("risks"), list):
        result["risks"] = parsed["risks"]

    return result
