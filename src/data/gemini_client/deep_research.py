"""Gemini Deep Research API 래퍼 (KIK-731 / KIK-733).

단발성 DeepResearch 태스크 호출:
- 비용 가드: 실행 전 예상 비용 산정
- 월타임 가드: 30분 하드 취소
- 하드 캡: 호출당 1 태스크(재귀 없음)
- 메타 로그: 호출마다 data/logs/deepthink_meta.jsonl 에 1건 추가
- 비활성 스위치: DEEPTHINK_DR_ENABLED=off 면 실행 생략

KIK-733: API 계약 수정.
- 엔드포인트: POST /v1beta/interactions  (generateContent 아님 — DR 모델은 Interactions API 만 지원)
- 필수 바디: {"agent": "<dr-model>", "input": [{"role":"user","content":<theme>}], "background": true}
- 폴링: GET /v1beta/interactions/{id}  (operations/* 아님)
- 응답: outputs[].content[].text + outputs[].annotations[].url

중요: 이것은 툴이지 에이전트가 아니다. 호출 시점은 호출자(DeepThink Step 3)가
config/tools.yaml 의 `when`/`strength`/`not_for` 를 보고 결정한다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from src.data.deepthink_meta import META_LOG_PATH as _META_LOG_PATH

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "deep-research-preview-04-2026"

# depth 별 예상 비용(USD). 실행 전 표시 + 월간 추적용.
_DEPTH_COST_USD = {
    "light": 1.5,
    "medium": 2.5,
    "deep": 5.0,
}
# KIK-737: Gemini 롱컨텍스트 티어 단가(USD / 1k 토큰). 추후 yaml 로 분리 가능.
_GEMINI_LONG_CONTEXT_PRICING_PER_1K = {
    "input_tokens": 0.00125,
    "output_tokens": 0.005,
    "thinking_tokens": 0.005,
    "tool_tokens": 0.0001,
}

# KIK-737: 하드 월타임. light/medium=15분, deep=30분.
_WALL_TIME_BY_DEPTH = {
    "light": 900,
    "medium": 900,
    "deep": 1800,
}
_DEFAULT_TIMEOUT_SEC = _WALL_TIME_BY_DEPTH["medium"]  # 하위 호환
_POLL_INTERVAL_SEC = 10


def is_available() -> bool:
    """GEMINI_API_KEY 가 설정되어 있으면 True."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def is_deep_research_enabled() -> bool:
    """DEEPTHINK_DR_ENABLED=off 면 False (킬 스위치)."""
    return os.environ.get("DEEPTHINK_DR_ENABLED", "on").lower() != "off"


def is_dry_run() -> bool:
    """KIK-737: DEEPTHINK_DRY_RUN=1 이면 True (모든 호출을 dry_run 으로 강제)."""
    return os.environ.get("DEEPTHINK_DRY_RUN", "").lower() in ("1", "on", "true")


def calc_actual_cost_usd(usage_metadata: dict) -> float:
    """KIK-737: Gemini DR usage_metadata 로 실제 비용을 계산한다.

    기대 키 (Gemini /v1beta/interactions 응답):
      input_tokens, output_tokens, thinking_tokens, tool_tokens
    없는 키는 0 으로 취급한다.
    """
    if not isinstance(usage_metadata, dict):
        return 0.0
    total = 0.0
    for key, price_per_1k in _GEMINI_LONG_CONTEXT_PRICING_PER_1K.items():
        tokens = float(usage_metadata.get(key) or 0)
        total += (tokens / 1000.0) * price_per_1k
    return round(total, 4)


def gemini_deep_research(
    theme: str,
    depth: str = "medium",
    budget_usd: float = 3.0,
    timeout_sec: int | None = None,
    model: str = _DEFAULT_MODEL,
    dry_run: bool = False,
) -> dict[str, Any]:
    """/v1beta/interactions 로 Gemini Deep Research 태스크 1건을 실행한다.

    KIK-737:
      - timeout_sec=None 이면 depth 연동 기본값(light/medium=15분, deep=30분)
      - dry_run=True 면 API 를 호출하지 않고 estimate 만 반환
      - DEEPTHINK_DRY_RUN=1 환경 변수로 모든 호출을 dry_run 강제

    Returns
    -------
    dict 키:
        text             : str
        sources          : list[str]
        cost_usd         : float    # 예상 비용(실행 전)
        actual_cost_usd  : float    # 실제 토큰 기준 비용 (KIK-737, status=ok 일 때만)
        duration_sec     : float
        status           : "ok" | "budget_exceeded" | "disabled" | "no_api_key" | "timeout" | "error" | "dry_run"
        error_message    : str | None
        interaction_id   : str | None
        usage_metadata   : dict | None   # KIK-737
    """
    started_at = time.time()
    estimate = _DEPTH_COST_USD.get(depth, _DEPTH_COST_USD["medium"])
    if timeout_sec is None:
        timeout_sec = _WALL_TIME_BY_DEPTH.get(depth, _WALL_TIME_BY_DEPTH["medium"])

    # KIK-737: dry_run(개별 인자 OR 환경 변수) → API 불필요
    if dry_run or is_dry_run():
        return _make_result(
            theme, depth, estimate, started_at,
            status="dry_run",
            error_message="dry_run=True (no API call)",
        )

    if not is_deep_research_enabled():
        return _make_result(
            theme, depth, estimate, started_at,
            status="disabled",
            error_message="DEEPTHINK_DR_ENABLED=off",
        )

    if estimate > budget_usd:
        return _make_result(
            theme, depth, estimate, started_at,
            status="budget_exceeded",
            error_message=f"estimate ${estimate:.2f} > budget ${budget_usd:.2f}",
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _make_result(
            theme, depth, 0.0, started_at,
            status="no_api_key",
            error_message="GEMINI_API_KEY not set",
        )

    try:
        text, sources, interaction_id, usage_metadata = _run_deep_research(
            api_key, model, theme, timeout_sec,
        )
    except _DRTimeout as exc:
        return _make_result(
            theme, depth, estimate, started_at,
            status="timeout",
            error_message=f"wall_time exceeded {timeout_sec}s",
            interaction_id=getattr(exc, "interaction_id", None),
        )
    except (requests.RequestException, KeyError, ValueError) as exc:
        return _make_result(
            theme, depth, 0.0, started_at,
            status="error",
            error_message=f"{type(exc).__name__}: {exc}",
        )

    return _make_result(
        theme, depth, estimate, started_at,
        status="ok",
        text=text,
        sources=sources,
        interaction_id=interaction_id,
        usage_metadata=usage_metadata,
    )


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------


class _DRTimeout(Exception):
    """폴링이 wall_time 을 초과하면 발생."""

    def __init__(self, message: str = "", interaction_id: str | None = None):
        super().__init__(message)
        self.interaction_id = interaction_id


def _run_deep_research(
    api_key: str, model: str, theme: str, timeout_sec: int,
) -> tuple[str, list[str], str | None, dict]:
    """DR interaction 을 제출하고 완료 또는 월타임 초과까지 폴링한다.

    KIK-733: /v1beta/interactions 사용 (generateContent 아님).
    KIK-737: 튜플 4번째로 usage_metadata 반환.
    """
    submit_url = f"{_API_BASE}/interactions?key={api_key}"
    payload = {
        "agent": model,
        "input": [{"role": "user", "content": theme}],
        "background": True,
    }
    response = requests.post(submit_url, json=payload, timeout=60)
    response.raise_for_status()
    submit_body = response.json()

    interaction_id = submit_body.get("id")
    initial_status = submit_body.get("status")

    if initial_status == "completed":
        text, sources = _extract_text_and_sources(submit_body)
        usage = submit_body.get("usage_metadata") or {}
        return text, sources, interaction_id, usage

    if not interaction_id:
        raise ValueError(f"submit response missing 'id': {submit_body}")

    text, sources, usage = _poll_interaction(api_key, interaction_id, timeout_sec)
    return text, sources, interaction_id, usage


def _poll_interaction(
    api_key: str, interaction_id: str, timeout_sec: int,
) -> tuple[str, list[str], dict]:
    """장기 실행 interaction 을 완료 또는 데드라인까지 폴링한다.

    KIK-733: /v1beta/interactions/{id} 사용 (operations/* 아님).
    KIK-737: usage_metadata 반환.
    """
    deadline = time.time() + timeout_sec
    poll_url = f"{_API_BASE}/interactions/{interaction_id}?key={api_key}"
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL_SEC)
        r = requests.get(poll_url, timeout=30)
        r.raise_for_status()
        body = r.json()
        status = body.get("status")
        if status == "completed":
            text, sources = _extract_text_and_sources(body)
            usage = body.get("usage_metadata") or {}
            return text, sources, usage
        if status == "failed":
            raise ValueError(
                f"interaction failed: {body.get('error') or body.get('status')}"
            )
        # status == "in_progress" → 계속 폴링
    raise _DRTimeout(interaction_id=interaction_id)


def _extract_text_and_sources(body: dict) -> tuple[str, list[str]]:
    """Gemini DR /v1beta/interactions 응답에서 텍스트와 인용 URL 을 추출한다.

    KIK-733: outputs[].content[].text  +  outputs[].annotations[].url

    응답 형태:
      {
        "id": "v1_...",
        "status": "completed",
        "outputs": [
          {
            "type": "text",
            "content": [{"text": "..."}],
            "annotations": [{"url": "...", "title": "..."}]
          },
          ...
        ],
        "usage_metadata": {...}
      }
    """
    outputs = body.get("outputs") or []
    text_parts: list[str] = []
    sources: list[str] = []
    seen_urls: set[str] = set()

    for out in outputs:
        if not isinstance(out, dict):
            continue
        # 텍스트 내용
        for c in out.get("content") or []:
            if isinstance(c, dict) and "text" in c:
                text_parts.append(c["text"])
        # 인용 annotation
        for ann in out.get("annotations") or []:
            if isinstance(ann, dict):
                url = ann.get("url") or ann.get("uri")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(url)

    text = "\n".join(text_parts)
    return text, sources


def _make_result(
    theme: str, depth: str, cost_usd: float, started_at: float,
    *,
    status: str,
    text: str = "",
    sources: list[str] | None = None,
    error_message: str | None = None,
    interaction_id: str | None = None,
    usage_metadata: dict | None = None,
) -> dict[str, Any]:
    """결과 dict 를 만들고 메타 로그에 추가한다(실패해도 무시)."""
    duration = time.time() - started_at
    actual_cost = calc_actual_cost_usd(usage_metadata) if usage_metadata else 0.0
    result = {
        "text": text,
        "sources": sources or [],
        "cost_usd": cost_usd,
        "actual_cost_usd": actual_cost,
        "duration_sec": round(duration, 2),
        "status": status,
        "error_message": error_message,
        "interaction_id": interaction_id,
        "usage_metadata": usage_metadata,
    }
    _append_meta_log(theme, depth, result)
    return result


def _append_meta_log(theme: str, depth: str, result: dict) -> None:
    """data/logs/deepthink_meta.jsonl 에 최대한 추가한다(실패해도 무시)."""
    try:
        _META_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": "gemini_deep_research",
            "theme": theme,
            "depth": depth,
            "status": result["status"],
            "cost_usd": result["cost_usd"],
            "actual_cost_usd": result.get("actual_cost_usd", 0.0),
            "sources_count": len(result["sources"]),
            "duration_sec": result["duration_sec"],
            "error_message": result.get("error_message"),
            "interaction_id": result.get("interaction_id"),
        }
        with open(_META_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[gemini_dr] meta log write failed: {exc}", file=sys.stderr)
