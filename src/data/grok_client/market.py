"""시장 관련 Grok API 함수: search_market, search_trending_stocks, get_trending_themes.

KIK-508 서브모듈 분할 시 grok_client.py 에서 추출.
"""

from typing import Optional

from src.data.grok_client._common import (
    EMPTY_MARKET,
    EMPTY_TRENDING,
    EMPTY_TRENDING_THEMES,
    _call_grok_api,
    _parse_json_response,
    _parse_json_array_response,
)

# 지원 지역은 한국(kr)·미국(us) 두 가지뿐. 알 수 없는 지역은 kr 로 폴백한다.
_DEFAULT_REGION = "kr"

# region → (라벨, 거래소 설명, 티커 접미사, 예시 티커)
# us 프롬프트는 영어이므로 라벨도 영어로 둔다.
_REGION_DESC = {
    "kr": ("한국 주식", "Korea Exchange (KOSPI/KOSDAQ)", ".KS/.KQ", "005930.KS"),
    "us": ("US stocks", "US stock exchanges (NYSE/NASDAQ)", "", "AAPL, MSFT"),
}

# region 입력 별칭 → 정규 코드. 모르는 값은 _DEFAULT_REGION 으로 폴백한다.
_REGION_ALIASES = {
    "kr": "kr", "korea": "kr", "한국": "kr", "국내": "kr", "south korea": "kr",
    "us": "us", "usa": "us", "미국": "us", "united states": "us", "america": "us",
}


def normalize_region(region: Optional[str]) -> str:
    """region 문자열을 kr/us 로 정규화한다 (대소문자·공백·한글 별칭 허용)."""
    key = (region or "").strip().lower()
    return _REGION_ALIASES.get(key, _DEFAULT_REGION)

# 트렌드 테마 탐색용 지역 라벨 (KIK-440)
_THEME_REGION_DESC = {
    "kr": "한국 시장",
    "us": "미국 시장",
}


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------

def _build_trending_prompt(region: str = _DEFAULT_REGION, theme: Optional[str] = None) -> str:
    """X 에서 화제가 되는 종목을 찾는 프롬프트를 만든다.

    kr 은 한국어 프롬프트, us 는 영어 프롬프트. 알 수 없는 region 은 kr 로 폴백.
    """
    region_key = normalize_region(region)
    label, exchange, suffix, example = _REGION_DESC[region_key]

    theme_part = f"\nFocus specifically on the theme/sector: {theme}" if theme else ""

    if suffix:
        suffix_inst = (
            f"Use Yahoo Finance ticker format with suffix '{suffix}' "
            f"(e.g., {example} for Samsung Electronics; KOSPI uses .KS, KOSDAQ uses .KQ)."
        )
    else:
        suffix_inst = f"Use standard Yahoo Finance ticker symbols (e.g., {example})."

    if region_key == "kr":
        return (
            f"X(Twitter)에서 지금 투자자들 사이에 화제가 되고 있는 {label}을 검색해 주세요."
            f"{theme_part}\n\n"
            f"실적 서프라이즈, 신제품 발표, 규제 변화, 업종 트렌드, 외국인·기관 수급 등으로 "
            f"주목받는 종목을 10~20개 찾아 주세요.\n"
            f"각 종목에 대해 티커 심볼과 화제가 된 이유를 제공해 주세요.\n\n"
            f"중요: {suffix_inst}\n"
            f"Yahoo Finance 에서 조회 가능한 실제 티커만 반환해 주세요.\n\n"
            f"JSON 형식으로 답변:\n"
            f'{{\n'
            f'  "stocks": [\n'
            f'    {{"ticker": "심볼", "name": "기업명", "reason": "화제 이유"}}\n'
            f'  ],\n'
            f'  "market_context": "X 상의 시장 센티먼트 요약"\n'
            f'}}'
        )
    return (
        f"Search X (Twitter) for stocks that are currently trending or heavily discussed "
        f"among investors in the {label} ({exchange}) market.{theme_part}\n\n"
        f"Find 10-20 stocks getting significant attention on X right now. "
        f"For each stock, provide the ticker symbol and a brief reason WHY it is trending.\n\n"
        f"IMPORTANT: {suffix_inst}\n"
        f"Return ONLY valid, real ticker symbols that can be looked up on Yahoo Finance.\n\n"
        f"Respond in JSON format:\n"
        f'{{\n'
        f'  "stocks": [\n'
        f'    {{"ticker": "SYMBOL", "name": "Company Name", "reason": "Why it is trending"}}\n'
        f'  ],\n'
        f'  "market_context": "Brief summary of the current market mood on X"\n'
        f'}}'
    )


def _build_market_prompt(market_or_index: str, context: str = "") -> str:
    """시장 리서치용 프롬프트를 만든다 (항상 한국어)."""
    context_block = f"{context}\n\n" if context else ""
    return (
        f"{context_block}"
        f"'{market_or_index}' 의 최신 시장 개황을 X(Twitter)와 웹 정보를 바탕으로 조사해 주세요.\n\n"
        f"1. 최근 가격 움직임과 요인\n"
        f"2. 거시경제 영향(금리·환율·원자재)\n"
        f"3. 센티먼트(강세/약세 균형)\n"
        f"4. 주목 이벤트·경제지표 일정\n"
        f"5. 섹터 로테이션 조짐\n\n"
        f"JSON 형식으로 답변:\n"
        f'{{\n'
        f'  "price_action": "최근 가격 움직임 요약",\n'
        f'  "macro_factors": ["요인1", "요인2"],\n'
        f'  "sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "요약"\n'
        f'  }},\n'
        f'  "upcoming_events": ["이벤트1", "이벤트2"],\n'
        f'  "sector_rotation": ["조짐1", "조짐2"]\n'
        f'}}'
    )


def _build_trending_themes_prompt(region: str = _DEFAULT_REGION) -> str:
    """트렌드 투자 테마 탐색용 프롬프트를 만든다 (KIK-440). 알 수 없는 region 은 kr 로 폴백."""
    label = _THEME_REGION_DESC[normalize_region(region)]
    valid_keys = "ai, ev, cloud-saas, cybersecurity, biotech, renewable-energy, fintech, defense, healthcare"

    return (
        f"X(Twitter)와 웹 정보를 바탕으로, 지금 {label}에서 투자자들이 주목하는 "
        f"섹터·투자 테마를 조사해 주세요.\n\n"
        f"모멘텀이 있는 테마를 3~5개 특정하고, 각 테마에 대해:\n"
        f"- 왜 지금 주목받는지(간결한 이유)\n"
        f"- 신뢰도(0.0~1.0)\n"
        f"를 제공해 주세요.\n\n"
        f"중요: theme 은 다음 키 중 하나로 반환해 주세요:\n"
        f"{valid_keys}\n\n"
        f"JSON 형식으로 답변:\n"
        f"[\n"
        f'  {{"theme": "테마키", "reason": "주목 이유(한국어)", "confidence": 0.85}}\n'
        f"]"
    )


# ---------------------------------------------------------------------------
# 공개 검색 함수
# ---------------------------------------------------------------------------

def search_market(
    market_or_index: str,
    timeout: int = 30,
    context: str = "",
) -> dict:
    """X·웹 검색으로 시장 또는 지수를 조사한다.

    Parameters
    ----------
    market_or_index : str
        시장명 또는 지수 (예: "KOSPI", "S&P500").
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        스키마는 EMPTY_MARKET 참조.
    """
    raw_text = _call_grok_api(_build_market_prompt(market_or_index, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_MARKET)

    result = dict(EMPTY_MARKET)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("price_action"), str):
        result["price_action"] = parsed["price_action"]
    if isinstance(parsed.get("macro_factors"), list):
        result["macro_factors"] = parsed["macro_factors"]

    sentiment = parsed.get("sentiment")
    if isinstance(sentiment, dict):
        score = sentiment.get("score", 0.0)
        result["sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": sentiment.get("summary", "") if isinstance(sentiment.get("summary"), str) else "",
        }

    if isinstance(parsed.get("upcoming_events"), list):
        result["upcoming_events"] = parsed["upcoming_events"]
    if isinstance(parsed.get("sector_rotation"), list):
        result["sector_rotation"] = parsed["sector_rotation"]

    return result


def search_trending_stocks(
    region: str = _DEFAULT_REGION,
    theme: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """특정 지역 시장에서 지금 화제인 종목을 X 에서 검색한다.

    Parameters
    ----------
    region : str
        시장 지역 (kr/us). 기본 kr.
    theme : str | None
        테마/섹터 필터 (AI/반도체/EV 등).
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        키: stocks (list of {ticker, name, reason}),
            market_context (str), raw_response (str).
    """
    raw_text = _call_grok_api(_build_trending_prompt(region, theme), timeout)
    if not raw_text:
        return dict(EMPTY_TRENDING)

    result = dict(EMPTY_TRENDING)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    stocks_raw = parsed.get("stocks")
    if isinstance(stocks_raw, list):
        validated = []
        for item in stocks_raw:
            if isinstance(item, dict) and isinstance(item.get("ticker"), str):
                validated.append({
                    "ticker": item["ticker"].strip(),
                    "name": item.get("name", "") if isinstance(item.get("name"), str) else "",
                    "reason": item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                })
        result["stocks"] = validated

    if isinstance(parsed.get("market_context"), str):
        result["market_context"] = parsed["market_context"]

    return result


def get_trending_themes(
    region: str = _DEFAULT_REGION,
    timeout: int = 30,
) -> dict:
    """Grok X/웹 검색으로 트렌드 투자 테마를 탐색한다 (KIK-440).

    Parameters
    ----------
    region : str
        테마 탐색 대상 지역 (kr/us). 기본 kr.
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        키: themes (list of {theme, reason, confidence}),
            raw_response (str).
    """
    raw_text = _call_grok_api(_build_trending_themes_prompt(region), timeout)
    if not raw_text:
        return dict(EMPTY_TRENDING_THEMES)

    result = dict(EMPTY_TRENDING_THEMES)
    result["raw_response"] = raw_text

    # 배열 우선(기대 형식), 없으면 "themes" 키를 가진 객체
    parsed = _parse_json_array_response(raw_text)
    if not parsed:
        obj = _parse_json_response(raw_text)
        parsed = obj.get("themes", []) if isinstance(obj.get("themes"), list) else []

    validated = []
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("theme"), str):
            validated.append({
                "theme": item["theme"].strip().lower(),
                "reason": item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                "confidence": float(item.get("confidence", 0.5)) if isinstance(item.get("confidence"), (int, float)) else 0.5,
            })
    validated.sort(key=lambda x: x["confidence"], reverse=True)
    result["themes"] = validated
    return result
