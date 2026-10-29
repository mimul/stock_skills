"""Semantic summary template builders for Neo4j vector search (KIK-420).

Each function generates a concise natural-language summary (max 200 chars)
from structured data. These summaries are embedded via TEI and stored as
`semantic_summary` on Neo4j nodes for vector similarity search.

No LLM required -- all summaries are template-based.
"""


def _trunc(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_screen_summary(
    screen_date: str,
    preset: str,
    region: str,
    top_symbols: list[str] | None = None,
) -> str:
    """Build summary for a Screen node.

    Example: "kr alpha 2026-02-18 / Top: 005930.KS, 000660.KS, 247540.KQ"
    """
    parts = []
    if region:
        parts.append(region)
    if preset:
        parts.append(preset)
    if screen_date:
        parts.append(screen_date)
    base = " ".join(parts)
    if top_symbols:
        syms = ", ".join(top_symbols[:5])
        base += f" / Top: {syms}"
    return _trunc(base)


def build_report_summary(
    symbol: str,
    name: str = "",
    score: float = 0,
    verdict: str = "",
    sector: str = "",
) -> str:
    """Build summary for a Report node.

    Example: "005930.KS 삼성전자 / Technology / 다소 저평가(54.8)"
    """
    parts = []
    label = f"{symbol} {name}".strip() if name else (symbol or "")
    if label:
        parts.append(label)
    if sector:
        parts.append(sector)
    if verdict:
        score_str = f"({score:.1f})" if score else ""
        parts.append(f"{verdict}{score_str}")
    return _trunc(" / ".join(parts))


def build_trade_summary(
    trade_date: str,
    trade_type: str,
    symbol: str,
    shares: int = 0,
    memo: str = "",
) -> str:
    """Build summary for a Trade node.

    Example: "2026-02-17 SELL 015760.KS 100주 / 헬스체크 후 매도"
    """
    action = trade_type.upper() if trade_type else "TRADE"
    parts = [f"{trade_date} {action} {symbol}"]
    if shares:
        parts[0] += f" {shares}주"
    if memo:
        parts.append(memo)
    return _trunc(" / ".join(parts))


def build_health_summary(
    health_date: str,
    summary: dict | None = None,
) -> str:
    """Build summary for a HealthCheck node.

    Example: "2026-02-18 헬스체크 / 전체 5종목 / 건전3 주의1 EXIT1"
    """
    parts = [f"{health_date} 헬스체크"]
    if summary:
        total = summary.get("total", 0)
        healthy = summary.get("healthy", 0)
        early = summary.get("early_warning", 0)
        caution = summary.get("caution", 0)
        exit_count = summary.get("exit", 0)
        parts.append(f"전체 {total}종목")
        detail = []
        if healthy:
            detail.append(f"건전{healthy}")
        if early:
            detail.append(f"주의{early}")
        if caution:
            detail.append(f"경계{caution}")
        if exit_count:
            detail.append(f"EXIT{exit_count}")
        if detail:
            parts.append(" ".join(detail))
    return _trunc(" / ".join(parts))


def build_research_summary(
    research_type: str,
    target: str,
    result: dict,
) -> str:
    """Build summary for a Research node.

    Ported from history_store._build_research_summary() with same logic.
    """
    grok = result.get("grok_research")
    if grok is None or not isinstance(grok, dict):
        grok = {}

    parts: list[str] = []

    if research_type == "stock":
        name = result.get("name", "")
        if name:
            parts.append(name)
        news = grok.get("recent_news") or result.get("news") or []
        if news and isinstance(news, list) and isinstance(news[0], (str, dict)):
            headline = news[0] if isinstance(news[0], str) else news[0].get("title", "")
            headline = headline.split("<")[0].strip()
            if headline:
                parts.append(headline[:80])
        xs = grok.get("x_sentiment") or result.get("x_sentiment") or {}
        if isinstance(xs, dict) and xs.get("score") is not None:
            parts.append(f"X센티먼트{xs['score']}")
        vs = result.get("value_score")
        if vs is not None:
            parts.append(f"점수{vs}")

    elif research_type == "market":
        pa = grok.get("price_action", "")
        if pa:
            if isinstance(pa, list):
                pa = "\n".join(pa)
            pa_clean = pa.split("<")[0].strip()
            parts.append(pa_clean[:120])
        sent = grok.get("sentiment") or {}
        if isinstance(sent, dict) and sent.get("score") is not None:
            parts.append(f"센티먼트{sent['score']}")

    elif research_type == "industry":
        trends = grok.get("trends", "")
        if trends:
            if isinstance(trends, list):
                trends = "\n".join(trends)
            trends_clean = trends.split("<")[0].strip()
            parts.append(trends_clean[:120])

    elif research_type == "business":
        name = result.get("name", "")
        if name:
            parts.append(name)
        overview = grok.get("overview", "")
        if overview:
            if isinstance(overview, list):
                overview = "\n".join(overview)
            overview_clean = overview.split("<")[0].strip()
            parts.append(overview_clean[:120])

    summary = ". ".join(parts)
    return _trunc(summary)


def build_market_context_summary(
    context_date: str,
    indices: list[dict] | None = None,
    grok_research: dict | None = None,
) -> str:
    """Build summary for a MarketContext node.

    Example: "2026-02-18 / KOSPI 2650 / VIX 20.29 / 테크→가치주 순환"
    """
    parts = [context_date]
    if indices:
        for idx in indices[:3]:
            name = idx.get("name", idx.get("symbol", ""))
            price = idx.get("price", idx.get("close", ""))
            if name and price:
                parts.append(f"{name}{price}")
    if grok_research and isinstance(grok_research, dict):
        rot = grok_research.get("sector_rotation")
        if isinstance(rot, list) and rot:
            parts.append(str(rot[0])[:50])
        sent = grok_research.get("sentiment")
        if isinstance(sent, dict) and sent.get("summary"):
            parts.append(str(sent["summary"])[:50])
    return _trunc(" / ".join(parts))


def build_note_summary(
    symbol: str = "",
    note_type: str = "",
    content: str = "",
    category: str = "",
    trigger: str = "",
    expected_action: str = "",
) -> str:
    """Build summary for a Note node.

    Example: "005930.KS thesis: AI 서버용 메모리 수요 증가"
    Example (no symbol): "[portfolio] review: PF 전체 회고"
    Example (lesson): "투자 lesson: 고점 매수했다 → 다음엔 RSI 확인 후 매수"
    """
    # KIK-534: lesson with trigger/expected_action gets a special format
    if note_type == "lesson" and (trigger or expected_action):
        parts = []
        if symbol:
            parts.append(symbol)
        elif category and category != "stock":
            parts.append(f"[{category}]")
        parts.append("투자 lesson:")
        if trigger and expected_action:
            parts.append(f"{trigger} → {expected_action}")
        elif trigger:
            parts.append(trigger)
        elif expected_action:
            parts.append(f"→ {expected_action}")
        if content:
            parts.append(content)
        return _trunc(" ".join(parts))

    parts = []
    if symbol:
        parts.append(symbol)
    elif category and category != "stock":
        parts.append(f"[{category}]")
    if note_type:
        parts.append(f"{note_type}:")
    if content:
        parts.append(content)
    return _trunc(" ".join(parts))


def build_watchlist_summary(
    name: str = "",
    symbols: list[str] | None = None,
) -> str:
    """Build summary for a Watchlist node.

    Example: "main watchlist: 005930.KS, AAPL, 247540.KQ"
    """
    parts = []
    if name:
        parts.append(f"{name} watchlist:")
    if symbols:
        parts.append(", ".join(symbols[:10]))
    return _trunc(" ".join(parts))


def build_stress_test_summary(
    test_date: str,
    scenario: str = "",
    portfolio_impact: float = 0,
    symbol_count: int = 0,
) -> str:
    """Build summary for a StressTest node (KIK-428).

    Example: "2026-02-19 스트레스테스트 / 트리플 약세 / 14종목 / PF영향+1.1%"
    """
    parts = [f"{test_date} 스트레스테스트"]
    if scenario:
        parts.append(scenario)
    if symbol_count:
        parts.append(f"{symbol_count}종목")
    if portfolio_impact:
        parts.append(f"PF영향{portfolio_impact * 100:+.1f}%")
    return _trunc(" / ".join(parts))


def build_forecast_summary(
    forecast_date: str,
    optimistic: float | None = None,
    base: float | None = None,
    pessimistic: float | None = None,
    symbol_count: int = 0,
) -> str:
    """Build summary for a Forecast node (KIK-428).

    Example: "2026-02-19 예측 / 14종목 / 베이스+14.4%"
    """
    parts = [f"{forecast_date} 예측"]
    if symbol_count:
        parts.append(f"{symbol_count}종목")
    if base is not None:
        parts.append(f"베이스{base * 100:+.1f}%")
    if optimistic is not None:
        parts.append(f"낙관{optimistic * 100:+.1f}%")
    if pessimistic is not None:
        parts.append(f"비관{pessimistic * 100:+.1f}%")
    return _trunc(" / ".join(parts))
