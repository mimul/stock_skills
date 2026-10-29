"""자연어 → 그래프 쿼리 디스패처 (KIK-409 Phase 1).

템플릿 매칭 엔진: 정규식 패턴 → graph_query 함수 → 마크다운 포맷.
템플릿에 매칭되지 않거나 Neo4j 를 사용할 수 없으면 None 을 반환한다.
"""

import re
from typing import Optional

from src.data.ticker_utils import SYMBOL_PATTERN, extract_symbol
from src.data import graph_query

# 하위 호환 별칭 (테스트가 이 모듈에서 _extract_symbol 을 import 한다)
_extract_symbol = extract_symbol


def _extract_symbol_and_type(text: str) -> dict:
    """텍스트에서 심볼과 리서치 유형을 추출한다."""
    symbol = _extract_symbol(text)
    rtype = "stock"
    if any(w in text for w in ("업계", "업종", "섹터", "산업", "industry")):
        rtype = "industry"
    elif any(w in text for w in ("시장", "마켓", "시황", "market")):
        rtype = "market"
    elif any(w in text for w in ("비즈니스", "사업", "business")):
        rtype = "business"
    return {"symbol": symbol, "research_type": rtype}


# ---------------------------------------------------------------------------
# 템플릿: (패턴, 쿼리 유형, 파라미터 추출기)
# ---------------------------------------------------------------------------

_TEMPLATES = [
    # 스트레스 테스트·포캐스트는 "지난번 …" 표현이 흔하므로 prior_report 보다 앞에 둔다 (KIK-428)
    (r"지난.*스트레스.*테스트|스트레스.*테스트.*이력|스트레스.*결과", "stress_test_history", _extract_symbol),
    (r"포캐스트.*추이|이전.*전망|예측.*이력|전망.*이력|forecast.*이력", "forecast_history", _extract_symbol),
    (r"지난번.*(리포트|보고서|분석)|지난.*리포트|이전.*리포트|과거.*리포트|직전.*리포트|최근.*리포트|이전.*보고서|prior.*report", "prior_report", _extract_symbol),
    (r"몇.*번.*스크리닝|반복.*후보|빈출|단골|자주.*나오|recurring", "recurring_picks", None),
    (r"리서치.*이력|리서치.*기록|전에.*조사|조사.*이력|research.*history", "research_chain", _extract_symbol_and_type),
    (r"최근.*시장|시황|마켓.*컨텍스트|시장.*상황|market.*context", "market_context", None),
    (r"거래.*이력|매매.*기록|매수.*이유|(?<![가-힣])산\s*이유|샀.*이유|트레이드.*기록|trade.*history", "trade_context", _extract_symbol),
    (r"자주.*나오.*안.*샀|빈출.*미매수|매수.*잊", "recurring_picks", None),
    (r"메모|노트.*목록|기록.*보여|투자.*메모", "notes", _extract_symbol),
    # KIK-413 시맨틱 서브노드 쿼리
    (r"뉴스.*이력|과거.*뉴스|뉴스.*목록|뉴스.*히스토리", "stock_news", _extract_symbol),
    (r"센티먼트.*추이|감정.*추이|센티먼트.*이력|sentiment.*trend", "sentiment_trend", _extract_symbol),
    (r"카탈리스트|(?<!원)재료|catalyst|호재|악재", "catalysts", _extract_symbol),
    (r"밸류에이션.*추이|PER.*추이|스코어.*추이|점수.*추이|리포트.*추이", "report_trend", _extract_symbol),
    (r"이벤트|일정(?!\s*(비율|한|량|수준|부분|기간))|upcoming|향후.*예정|앞으로.*예정", "upcoming_events", None),
    (r"지표.*추이|VIX.*추이|인디케이터|매크로.*지표", "indicator_history", None),
    # KIK-603 테마 트렌드
    (r"테마.*추이|테마.*트렌드|테마.*이력|트렌드.*테마.*이력|theme.*trend", "theme_trends", None),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), qtype, extractor) for pat, qtype, extractor in _TEMPLATES]


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def query(user_input: str) -> Optional[dict]:
    """사용자 입력을 템플릿에 매칭하고 해당 그래프 쿼리를 실행한다.

    Returns:
        {"query_type": str, "result": any, "formatted": str} 또는 매칭 없으면 None.
    """
    for pattern, query_type, extractor in _COMPILED:
        if not pattern.search(user_input):
            continue

        params = {}
        if extractor is not None:
            extracted = extractor(user_input)
            if isinstance(extracted, dict):
                params = extracted
            else:
                params = {"symbol": extracted}

        result = _execute(query_type, params)
        if result is None:
            return None

        formatted = format_result(query_type, result, params)
        return {"query_type": query_type, "result": result, "formatted": formatted}

    return None


# ---------------------------------------------------------------------------
# 실행 디스패처
# ---------------------------------------------------------------------------

def _execute(query_type: str, params: dict):
    """쿼리 유형에 맞는 graph_query 함수로 디스패치한다."""
    if query_type == "prior_report":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_prior_report(symbol)

    if query_type == "recurring_picks":
        return graph_query.get_recurring_picks()

    if query_type == "research_chain":
        symbol = params.get("symbol")
        rtype = params.get("research_type", "stock")
        if not symbol:
            return None
        return graph_query.get_research_chain(rtype, symbol)

    if query_type == "market_context":
        return graph_query.get_recent_market_context()

    if query_type == "trade_context":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_trade_context(symbol)

    if query_type == "notes":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_trade_context(symbol)

    # KIK-413 시맨틱 쿼리
    if query_type == "stock_news":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_stock_news_history(symbol)

    if query_type == "sentiment_trend":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_sentiment_trend(symbol)

    if query_type == "catalysts":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_catalysts(symbol)

    if query_type == "report_trend":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_report_trend(symbol)

    if query_type == "upcoming_events":
        return graph_query.get_upcoming_events()

    if query_type == "indicator_history":
        return graph_query.get_recent_market_context()

    # KIK-428
    if query_type == "stress_test_history":
        symbol = params.get("symbol")
        return graph_query.get_stress_test_history(symbol=symbol)

    if query_type == "forecast_history":
        symbol = params.get("symbol")
        return graph_query.get_forecast_history(symbol=symbol)

    # KIK-603
    if query_type == "theme_trends":
        return graph_query.get_theme_trends()

    return None


# ---------------------------------------------------------------------------
# 포매터
# ---------------------------------------------------------------------------

def format_result(query_type: str, result, params: dict) -> str:
    """쿼리 결과를 마크다운으로 포맷한다."""
    formatter = _FORMATTERS.get(query_type)
    if formatter:
        return formatter(result, params)
    return str(result)


def _fmt_prior_report(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    if not result:
        return f"{symbol} 의 과거 리포트를 찾을 수 없습니다."
    return (
        f"## {symbol} 의 지난 리포트\n\n"
        f"- 날짜: {result.get('date', '-')}\n"
        f"- 스코어: {result.get('score', '-')}\n"
        f"- 판정: {result.get('verdict', '-')}\n"
    )


def _fmt_recurring_picks(result, params: dict) -> str:
    if not result:
        return "반복 후보에 오른 미매수 종목이 없습니다."
    lines = ["## 반복 후보 (미매수)\n", "| 종목 | 출현 횟수 | 최종일 |", "|:-----|:---------|:-------|"]
    for r in result:
        lines.append(f"| {r.get('symbol', '-')} | {r.get('count', 0)} | {r.get('last_date', '-')} |")
    return "\n".join(lines)


def _fmt_research_chain(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    rtype = params.get("research_type", "stock")
    if not result:
        return f"{symbol} ({rtype}) 의 리서치 이력을 찾을 수 없습니다."
    lines = [f"## {symbol} 의 리서치 이력 ({rtype})\n", "| 날짜 | 요약 |", "|:-----|:---------|"]
    for r in result:
        summary = (r.get("summary") or "-")[:80]
        lines.append(f"| {r.get('date', '-')} | {summary} |")
    return "\n".join(lines)


def _fmt_market_context(result, params: dict) -> str:
    if not result:
        return "최근 시황 데이터를 찾을 수 없습니다."
    date = result.get("date", "-")
    indices = result.get("indices", [])
    lines = [f"## 시황 컨텍스트 ({date})\n"]
    if indices:
        lines.append("| 지표 | 값 |")
        lines.append("|:-----|:---|")
        for idx in indices:
            if isinstance(idx, dict):
                lines.append(f"| {idx.get('name', '-')} | {idx.get('value', '-')} |")
            else:
                lines.append(f"| {idx} | - |")
    else:
        lines.append("지표 데이터 없음")
    return "\n".join(lines)


def _fmt_trade_context(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    trades = result.get("trades", [])
    notes = result.get("notes", [])
    if not trades and not notes:
        return f"{symbol} 의 거래 이력·메모를 찾을 수 없습니다."
    lines = [f"## {symbol} 의 거래 컨텍스트\n"]
    if trades:
        lines.append("### 거래 이력\n")
        lines.append("| 날짜 | 구분 | 주수 | 가격 |")
        lines.append("|:-----|:-----|:-----|:-----|")
        for t in trades:
            lines.append(f"| {t.get('date', '-')} | {t.get('type', '-')} | {t.get('shares', '-')} | {t.get('price', '-')} |")
    if notes:
        lines.append("\n### 메모\n")
        lines.append("| 날짜 | 유형 | 내용 |")
        lines.append("|:-----|:-------|:-----|")
        for n in notes:
            content = (n.get("content") or "-")[:50]
            lines.append(f"| {n.get('date', '-')} | {n.get('type', '-')} | {content} |")
    return "\n".join(lines)


def _fmt_notes(result, params: dict) -> str:
    return _fmt_trade_context(result, params)


def _fmt_stock_news(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    if not result:
        return f"{symbol} 의 뉴스 이력을 찾을 수 없습니다."
    lines = [f"## {symbol} 의 뉴스 이력\n",
             "| 날짜 | 출처 | 제목 |",
             "|:-----|:-------|:---------|"]
    for r in result:
        title = (r.get("title") or "-")[:80]
        lines.append(f"| {r.get('date', '-')} | {r.get('source', '-')} | {title} |")
    return "\n".join(lines)


def _fmt_sentiment_trend(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    if not result:
        return f"{symbol} 의 센티먼트 추이를 찾을 수 없습니다."
    lines = [f"## {symbol} 의 센티먼트 추이\n",
             "| 날짜 | 출처 | 스코어 | 요약 |",
             "|:-----|:-------|:-------|:---------|"]
    for r in result:
        summary = (r.get("summary") or "-")[:60]
        score = r.get("score", "-")
        lines.append(f"| {r.get('date', '-')} | {r.get('source', '-')} | {score} | {summary} |")
    return "\n".join(lines)


def _fmt_catalysts(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    pos = result.get("positive", [])
    neg = result.get("negative", [])
    if not pos and not neg:
        return f"{symbol} 의 카탈리스트 정보를 찾을 수 없습니다."
    lines = [f"## {symbol} 의 카탈리스트\n"]
    if pos:
        lines.append("### 긍정 재료\n")
        for p in pos:
            lines.append(f"- {(p or '-')[:100]}")
    if neg:
        lines.append("\n### 부정 재료\n")
        for n in neg:
            lines.append(f"- {(n or '-')[:100]}")
    return "\n".join(lines)


def _fmt_report_trend(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    if not result:
        return f"{symbol} 의 밸류에이션 추이를 찾을 수 없습니다."
    lines = [f"## {symbol} 의 밸류에이션 추이\n",
             "| 날짜 | 스코어 | 판정 | 주가 | PER | PBR |",
             "|:-----|:-------|:-----|:-----|:----|:----|"]
    for r in result:
        lines.append(
            f"| {r.get('date', '-')} | {r.get('score', '-')} | {r.get('verdict', '-')} "
            f"| {r.get('price', '-')} | {r.get('per', '-')} | {r.get('pbr', '-')} |"
        )
    return "\n".join(lines)


def _fmt_upcoming_events(result, params: dict) -> str:
    if not result:
        return "향후 이벤트 정보를 찾을 수 없습니다."
    lines = ["## 향후 이벤트\n"]
    for r in result:
        lines.append(f"- [{r.get('date', '-')}] {(r.get('text') or '-')[:100]}")
    return "\n".join(lines)


def _fmt_indicator_history(result, params: dict) -> str:
    """지표 쿼리는 market_context 포매터를 재사용한다."""
    return _fmt_market_context(result, params)


def _fmt_stress_test_history(result, params: dict) -> str:
    if not result:
        return "스트레스 테스트 이력을 찾을 수 없습니다."
    lines = ["## 스트레스 테스트 이력\n",
             "| 날짜 | 시나리오 | PF 영향 | VaR95 | VaR99 | 종목 수 |",
             "|:-----|:---------|:-------|:------|:------|:-------|"]
    for r in result:
        impact = r.get("portfolio_impact")
        impact_str = f"{impact * 100:+.1f}%" if impact is not None else "-"
        var95 = r.get("var_95")
        var95_str = f"{var95 * 100:.1f}%" if var95 else "-"
        var99 = r.get("var_99")
        var99_str = f"{var99 * 100:.1f}%" if var99 else "-"
        lines.append(
            f"| {r.get('date', '-')} | {r.get('scenario', '-')} "
            f"| {impact_str} | {var95_str} | {var99_str} | {r.get('symbol_count', '-')} |"
        )
    return "\n".join(lines)


def _fmt_forecast_history(result, params: dict) -> str:
    if not result:
        return "포캐스트 이력을 찾을 수 없습니다."
    lines = ["## 포캐스트 이력\n",
             "| 날짜 | 낙관 | 기본 | 비관 | 평가액(만원) | 종목 수 |",
             "|:-----|:-----|:-------|:-----|:------------|:-------|"]
    for r in result:
        opt = r.get("optimistic")
        opt_str = f"{opt * 100:+.1f}%" if opt is not None else "-"
        base = r.get("base")
        base_str = f"{base * 100:+.1f}%" if base is not None else "-"
        pess = r.get("pessimistic")
        pess_str = f"{pess * 100:+.1f}%" if pess is not None else "-"
        # total_value_krw 는 원(KRW) 단위 → 만원 단위로 환산해 표시
        total = r.get("total_value_krw")
        total_str = f"{total / 10000:,.0f}" if total else "-"
        lines.append(
            f"| {r.get('date', '-')} | {opt_str} | {base_str} "
            f"| {pess_str} | {total_str} | {r.get('symbol_count', '-')} |"
        )
    return "\n".join(lines)


def _fmt_theme_trends(result, params: dict) -> str:
    if not result:
        return "테마 트렌드 이력을 찾을 수 없습니다."
    lines = ["## 테마 트렌드 이력 (KIK-603)\n",
             "| 날짜 | 테마 | 신뢰도 | 순위 | 지역 | 이유 |",
             "|:-----|:-------|:-------|:-------|:-----|:-----|"]
    for r in result:
        conf = r.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "-"
        reason = (r.get("reason") or "-")[:60]
        lines.append(
            f"| {r.get('date', '-')} | {r.get('theme', '-')} "
            f"| {conf_str} | {r.get('rank', '-')} "
            f"| {r.get('region', '-')} | {reason} |"
        )
    return "\n".join(lines)


_FORMATTERS = {
    "prior_report": _fmt_prior_report,
    "recurring_picks": _fmt_recurring_picks,
    "research_chain": _fmt_research_chain,
    "market_context": _fmt_market_context,
    "trade_context": _fmt_trade_context,
    "notes": _fmt_notes,
    # KIK-413
    "stock_news": _fmt_stock_news,
    "sentiment_trend": _fmt_sentiment_trend,
    "catalysts": _fmt_catalysts,
    "report_trend": _fmt_report_trend,
    "upcoming_events": _fmt_upcoming_events,
    "indicator_history": _fmt_indicator_history,
    # KIK-428
    "stress_test_history": _fmt_stress_test_history,
    "forecast_history": _fmt_forecast_history,
    # KIK-603
    "theme_trends": _fmt_theme_trends,
}
