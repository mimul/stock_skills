"""종목 관련 Grok API 함수: search_stock_deep, search_x_sentiment.

KIK-508 서브모듈 분할 시 grok_client.py 에서 추출.
"""

from src.data.grok_client._common import (
    EMPTY_STOCK_DEEP,
    _call_grok_api,
    _contains_korean,
    _is_korean_stock,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------

def _build_sentiment_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """센티먼트 분석용 프롬프트를 만든다."""
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    return (
        f"{context_block}"
        f"Search X for recent posts about {symbol}{name_part} stock. "
        f"Analyze the sentiment of the posts and provide:\n"
        f"1. A list of positive factors (bullish signals) mentioned\n"
        f"2. A list of negative factors (bearish signals) mentioned\n"
        f"3. An overall sentiment score from -1.0 (very bearish) to 1.0 (very bullish)\n\n"
        f"Respond in JSON format:\n"
        f'{{"positive": ["factor1", "factor2"], '
        f'"negative": ["factor1", "factor2"], '
        f'"sentiment_score": 0.0}}'
    )


def _build_stock_deep_prompt(symbol: str, company_name: str = "", context: str = "") -> str:
    """심층 종목 리서치용 프롬프트를 만든다.

    한국 종목(.KS/.KQ)이거나 회사명에 한글이 있으면 한국어 프롬프트,
    그 외(미국 종목)는 영어 프롬프트를 사용한다. JSON 키는 동일하다.
    """
    name_part = f" ({company_name})" if company_name else ""
    context_block = f"{context}\n\n" if context else ""
    if _is_korean_stock(symbol) or _contains_korean(company_name):
        return (
            f"{context_block}"
            f"{symbol}{name_part} 에 대해 X(Twitter)와 웹의 최신 정보를 바탕으로 다음을 조사해 주세요.\n\n"
            f"1. 최근 주요 뉴스(최근 1~2주)\n"
            f"2. 실적에 영향을 주는 재료(긍정/부정)\n"
            f"3. 기관투자자·애널리스트의 시각\n"
            f"4. X 상의 투자자 센티먼트\n"
            f"5. 경쟁사 대비 주목할 점\n\n"
            f"JSON 형식으로 답변:\n"
            f'{{\n'
            f'  "recent_news": ["뉴스1", "뉴스2"],\n'
            f'  "catalysts": {{\n'
            f'    "positive": ["재료1", "재료2"],\n'
            f'    "negative": ["재료1", "재료2"]\n'
            f'  }},\n'
            f'  "analyst_views": ["견해1", "견해2"],\n'
            f'  "x_sentiment": {{\n'
            f'    "score": 0.0,\n'
            f'    "summary": "요약 텍스트",\n'
            f'    "key_opinions": ["의견1", "의견2"]\n'
            f'  }},\n'
            f'  "competitive_notes": ["주목점1", "주목점2"]\n'
            f'}}'
        )
    return (
        f"{context_block}"
        f"Research {symbol}{name_part} using X (Twitter) and web sources. Provide:\n\n"
        f"1. Key recent news (last 1-2 weeks)\n"
        f"2. Catalysts affecting earnings (positive/negative)\n"
        f"3. Institutional/analyst perspectives\n"
        f"4. X investor sentiment\n"
        f"5. Notable competitive dynamics\n\n"
        f"Respond in JSON:\n"
        f'{{\n'
        f'  "recent_news": ["news1", "news2"],\n'
        f'  "catalysts": {{\n'
        f'    "positive": ["catalyst1", "catalyst2"],\n'
        f'    "negative": ["catalyst1", "catalyst2"]\n'
        f'  }},\n'
        f'  "analyst_views": ["view1", "view2"],\n'
        f'  "x_sentiment": {{\n'
        f'    "score": 0.0,\n'
        f'    "summary": "summary text",\n'
        f'    "key_opinions": ["opinion1", "opinion2"]\n'
        f'  }},\n'
        f'  "competitive_notes": ["note1", "note2"]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# 공개 검색 함수
# ---------------------------------------------------------------------------

def search_x_sentiment(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
    context: str = "",
) -> dict:
    """Grok API 로 X 에서 종목 센티먼트를 검색한다.

    Parameters
    ----------
    symbol : str
        종목 티커 (예: "AAPL", "005930.KS").
    company_name : str
        검색 정확도를 높이기 위한 회사명.
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        키: positive (list[str]), negative (list[str]),
            sentiment_score (float, -1~1), raw_response (str).
        오류 또는 API 미사용 시 빈 결과를 반환한다.
    """
    empty_result = {
        "positive": [],
        "negative": [],
        "sentiment_score": 0.0,
        "raw_response": "",
    }

    raw_text = _call_grok_api(_build_sentiment_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return empty_result

    result = dict(empty_result)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if isinstance(parsed.get("positive"), list):
        result["positive"] = parsed["positive"]
    if isinstance(parsed.get("negative"), list):
        result["negative"] = parsed["negative"]
    score = parsed.get("sentiment_score")
    if isinstance(score, (int, float)):
        result["sentiment_score"] = max(-1.0, min(1.0, float(score)))

    return result


def search_stock_deep(
    symbol: str,
    company_name: str = "",
    timeout: int = 30,
    context: str = "",
) -> dict:
    """X·웹 검색으로 종목을 심층 리서치한다.

    Parameters
    ----------
    symbol : str
        티커 (예: "005930.KS", "AAPL").
    company_name : str
        프롬프트 정확도를 높이기 위한 회사명.
    timeout : int
        요청 타임아웃(초).

    Returns
    -------
    dict
        스키마는 EMPTY_STOCK_DEEP 참조.
    """
    raw_text = _call_grok_api(_build_stock_deep_prompt(symbol, company_name, context=context), timeout)
    if not raw_text:
        return dict(EMPTY_STOCK_DEEP)

    result = dict(EMPTY_STOCK_DEEP)
    result["raw_response"] = raw_text

    parsed = _parse_json_response(raw_text)
    if not parsed:
        return result

    if isinstance(parsed.get("recent_news"), list):
        result["recent_news"] = parsed["recent_news"]

    catalysts = parsed.get("catalysts")
    if isinstance(catalysts, dict):
        result["catalysts"] = {
            "positive": catalysts.get("positive", []) if isinstance(catalysts.get("positive"), list) else [],
            "negative": catalysts.get("negative", []) if isinstance(catalysts.get("negative"), list) else [],
        }

    if isinstance(parsed.get("analyst_views"), list):
        result["analyst_views"] = parsed["analyst_views"]

    x_sent = parsed.get("x_sentiment")
    if isinstance(x_sent, dict):
        score = x_sent.get("score", 0.0)
        result["x_sentiment"] = {
            "score": max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
            "summary": x_sent.get("summary", "") if isinstance(x_sent.get("summary"), str) else "",
            "key_opinions": x_sent.get("key_opinions", []) if isinstance(x_sent.get("key_opinions"), list) else [],
        }

    if isinstance(parsed.get("competitive_notes"), list):
        result["competitive_notes"] = parsed["competitive_notes"]

    return result
