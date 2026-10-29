"""Gemini Deep Research 실 API 계약 테스트 (KIK-733).

이 테스트는 **실제 Gemini DR API 를 호출**해 래퍼의 스키마 가정이 라이브
서비스와 일치하는지 검증한다. 비용이 들고($1.5~3/회) 호출당 5~15분이
걸리므로 환경 변수와 pytest 마커로 게이트한다.

활성화
------
1. `GEMINI_API_KEY` 설정
2. `DEEPTHINK_REAL_API_TEST=on` 명시적 설정
3. 실행: ``pytest -m real_api tests/integration/test_gemini_dr_real_api.py``

일반 `pytest tests/` 실행에서는 기본 스킵된다.

존재 이유
---------
KIK-731 은 실제 API 스키마와 맞지 않는 모의 테스트로 출시됐다.
버그(잘못된 엔드포인트·필드·응답 파싱)는 $4.9 짜리 프로덕션 호출이
실패하고서야 발견됐다. KIK-733 은 재발 방지를 위한 1회성 계약 검사로
이 실 API 테스트를 도입했다.

예산 가드: 월 상한은 deepthink_limits.yaml 이 강제한다. 이 테스트는
한 달에 몇 번만 실행해야 한다.
"""

from __future__ import annotations

import json
import os

import pytest

from src.data.gemini_client.deep_research import gemini_deep_research

pytestmark = pytest.mark.real_api


def _real_api_enabled() -> bool:
    return (
        os.environ.get("DEEPTHINK_REAL_API_TEST") == "on"
        and bool(os.environ.get("GEMINI_API_KEY"))
    )


REASON_SKIP = (
    "Real API test disabled. Set DEEPTHINK_REAL_API_TEST=on and GEMINI_API_KEY "
    "to run. Cost: $1.5–3 per call."
)


# ---------------------------------------------------------------------------
# 실 API 계약 테스트
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_light_depth_returns_sources(tmp_path, monkeypatch):
    """light depth 호출이 완료되고 소스를 1개 이상 반환해야 한다."""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="AI semiconductor 2026 outlook (KIK-733 contract test)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,  # 15min cap for tests
    )
    assert result["status"] == "ok", (
        f"expected ok, got {result['status']!r}: {result.get('error_message')}"
    )
    assert isinstance(result["text"], str) and len(result["text"]) > 0
    assert isinstance(result["sources"], list) and len(result["sources"]) > 0
    assert isinstance(result["interaction_id"], str)
    assert result["interaction_id"].startswith(("v1_", "interactions/"))


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_response_schema_matches_extraction(tmp_path, monkeypatch):
    """outputs[].content[].text + outputs[].annotations[].url 이 추출된다."""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="Test query — Bitcoin price 2026 (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    # 모든 소스는 유효한 http(s) URL 이어야 한다
    for src in result["sources"]:
        assert src.startswith(("http://", "https://")), f"non-URL source: {src!r}"
    # 실제 DR 응답이면 텍스트가 충분히 길어야 한다(>200자)
    assert len(result["text"]) > 200, f"text suspiciously short: {len(result['text'])}"


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_meta_log_written(tmp_path, monkeypatch):
    """실 호출 후 meta.jsonl 에 자동 추가된다."""
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH", log,
    )
    result = gemini_deep_research(
        theme="Test query — TSMC capex 2026 (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    assert log.exists()
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["tool"] == "gemini_deep_research"
    assert rec["status"] == "ok"
    assert rec["sources_count"] == len(result["sources"])
    assert rec["interaction_id"] == result["interaction_id"]


@pytest.mark.skipif(not _real_api_enabled(), reason=REASON_SKIP)
def test_real_api_polling_completes_within_timeout(tmp_path, monkeypatch):
    """background=true → 폴링 → completed 경로가 15분 이내에 완료된다."""
    monkeypatch.setattr(
        "src.data.gemini_client.deep_research._META_LOG_PATH",
        tmp_path / "log.jsonl",
    )
    result = gemini_deep_research(
        theme="Test query — short macro check (KIK-733)",
        depth="light",
        budget_usd=3.0,
        timeout_sec=900,
    )
    assert result["status"] == "ok"
    assert result["duration_sec"] < 900
