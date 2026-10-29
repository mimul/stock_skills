"""Morning summary: anomaly detection for portfolio (KIK-717).

Detects exit-rule hits, RSI extremes, upcoming earnings, and VIX spikes.
Pure data functions — no judgment, no recommendations.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np

from src.data.common import safe_float


# ---------------------------------------------------------------------------
# Alert types and thresholds
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS = {
    "exit_rule_pct": -15.0,       # exit-rule default (%)
    "hard_stop_pct": -20.0,       # hard stop loss (%)
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "earnings_days": 7,           # days before earnings to alert
    "vix_elevated": 25,
}


def _calc_rsi(closes, period: int = 14) -> float | None:
    """Calculate RSI(14) from close prices.

    Accepts list[float], numpy array, pandas Series, or DataFrame
    (Close column auto-extracted).
    """
    if hasattr(closes, "columns"):
        if "Close" in closes.columns:
            closes = closes["Close"].tolist()
        else:
            return None
    elif hasattr(closes, "tolist"):
        closes = closes.tolist()
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_alerts(
    positions: list[dict],
    infos: dict[str, dict],
    histories: dict[str, list[float]],
    vix_price: float | None = None,
    prev_alerts: list[dict] | None = None,
) -> list[dict]:
    """Detect anomalies across portfolio holdings.

    Parameters
    ----------
    positions : list[dict]
        Portfolio from load_portfolio().
    infos : dict[str, dict]
        {symbol: get_stock_info() result}.
    histories : dict[str, list[float]]
        {symbol: list of close prices (latest last)}.
    vix_price : float | None
        Current VIX value.
    prev_alerts : list[dict] | None
        Previous day's alerts for state-change filtering.

    Returns
    -------
    list[dict]
        List of alert dicts with keys: symbol, type, severity, message, value.
    """
    alerts = []
    thr = ALERT_THRESHOLDS
    prev_symbols_types = set()
    if prev_alerts:
        prev_symbols_types = {(a["symbol"], a["type"]) for a in prev_alerts}

    for pos in positions:
        sym = pos["symbol"]
        info = infos.get(sym)
        if not info:
            continue

        price = safe_float(info.get("price"))
        cost = safe_float(pos.get("cost_price"))

        # 1. Exit-rule: P&L threshold
        if price > 0 and cost > 0:
            pnl_pct = (price - cost) / cost * 100
            if pnl_pct <= thr["hard_stop_pct"]:
                alerts.append({
                    "symbol": sym, "type": "hard_stop",
                    "severity": "CRITICAL",
                    "message": f"손익 {pnl_pct:+.1f}% → 손절 라인(-20%) 도달",
                    "value": pnl_pct,
                })
            elif pnl_pct <= thr["exit_rule_pct"]:
                alerts.append({
                    "symbol": sym, "type": "exit_rule",
                    "severity": "CRITICAL",
                    "message": f"손익 {pnl_pct:+.1f}% → exit-rule(-15%) 도달",
                    "value": pnl_pct,
                })

        # 2. RSI extremes
        closes = histories.get(sym, [])
        rsi = _calc_rsi(closes)
        if rsi is not None:
            if rsi >= thr["rsi_overbought"]:
                alerts.append({
                    "symbol": sym, "type": "rsi_high",
                    "severity": "INFO",
                    "message": f"RSI {rsi:.1f} → 과매수권",
                    "value": rsi,
                })
            elif rsi <= thr["rsi_oversold"]:
                alerts.append({
                    "symbol": sym, "type": "rsi_low",
                    "severity": "INFO",
                    "message": f"RSI {rsi:.1f} → 과매도권",
                    "value": rsi,
                })

        # 3. Upcoming earnings
        next_earnings = pos.get("next_earnings") or ""
        if next_earnings:
            try:
                earn_date = datetime.strptime(next_earnings, "%Y-%m-%d").date()
                days_until = (earn_date - date.today()).days
                if 0 <= days_until <= thr["earnings_days"]:
                    alerts.append({
                        "symbol": sym, "type": "earnings_soon",
                        "severity": "INFO",
                        "message": f"실적 발표 {next_earnings} (D-{days_until})",
                        "value": days_until,
                    })
            except ValueError:
                pass

    # 4. VIX
    if vix_price is not None and vix_price >= thr["vix_elevated"]:
        alerts.append({
            "symbol": "^VIX", "type": "vix_high",
            "severity": "CRITICAL" if vix_price >= 30 else "INFO",
            "message": f"VIX {vix_price:.1f} → {'급등' if vix_price >= 30 else '경계 수준'}",
            "value": vix_price,
        })

    # 5. State-change filter: remove alerts that existed yesterday with same symbol+type
    if prev_alerts:
        alerts = [a for a in alerts
                  if (a["symbol"], a["type"]) not in prev_symbols_types]

    # Sort by severity (CRITICAL first)
    severity_order = {"CRITICAL": 0, "INFO": 1}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 2))

    return alerts


def format_morning_summary(alerts: list[dict], pf_total: float | None = None) -> str:
    """Format alerts into a human-readable morning summary.

    Parameters
    ----------
    alerts : list[dict]
        Output of detect_alerts().
    pf_total : float | None
        PF total value for context.

    Returns
    -------
    str
        Formatted summary string.
    """
    today_str = date.today().strftime("%m/%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][date.today().weekday()]

    if not alerts:
        return f"■ 아침 요약 ({today_str} {weekday})\n☀️ 이상 없음"

    lines = [f"■ 아침 요약 ({today_str} {weekday})"]

    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    info = [a for a in alerts if a["severity"] == "INFO"]

    total_count = len(alerts)
    lines.append(f"⚠️ 주의 {total_count}건")
    lines.append("")

    for a in critical[:3]:
        sym_display = a["symbol"]
        lines.append(f"🔴 {sym_display}: {a['message']}")

    for a in info[:5]:
        sym_display = a["symbol"]
        lines.append(f"🟡 {sym_display}: {a['message']}")

    if len(alerts) > 8:
        lines.append(f"  ...외 {len(alerts) - 8}건")

    # Suggest deepdive for most critical
    if critical:
        first = critical[0]
        if first["type"] in ("hard_stop", "exit_rule"):
            lines.append(f"\n→ 「{first['symbol']} 팔아야 해?」로 상세 분석")
        elif first["type"] == "vix_high":
            lines.append("\n→ 「리스크 판정해줘」로 시황 확인")
    elif info:
        first = info[0]
        if first["type"] == "earnings_soon":
            lines.append(f"\n→ 「{first['symbol']} 실적 발표 전 체크」로 확인")

    return "\n".join(lines)
