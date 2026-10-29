"""LLM Tool — 멀티 LLM 호출 파사드.

tools/ 층은 API 호출만 담당한다. 판단 로직은 포함하지 않는다.
Gemini / GPT / Grok 을 공통 인터페이스로 호출한다.
API 키 미설정 시 None 을 반환한다(호출자가 Claude 로 폴백).

KIK-686: web_search / reasoning 파라미터 추가.
  - Gemini: google_search tool 로 Grounding(Google 검색 통합)
  - GPT: reasoning_effort 로 추론 깊이를 4단계 제어 (none/low/medium/high)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# 프로젝트 루트의 .env 로드
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# API 엔드포인트
# ---------------------------------------------------------------------------

_ENDPOINTS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "gpt": "https://api.openai.com/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
}

_API_KEY_ENVS = {
    "gemini": "GEMINI_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "grok": "XAI_API_KEY",
}

_VALID_PROVIDERS = set(_ENDPOINTS.keys())


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def call_llm(
    provider: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    timeout: int = 60,
    web_search: bool = False,
    reasoning: Optional[str] = None,
) -> Optional[str]:
    """LLM 을 호출해 텍스트를 반환한다.

    Parameters
    ----------
    provider : str
        "gemini" | "gpt" | "grok"
    model : str
        모델명 (예: "gemini-3-flash-preview", "gpt-5.4", "grok-4.20-0309-reasoning")
    prompt : str
        사용자 프롬프트
    system_prompt : str, optional
        시스템 프롬프트
    timeout : int
        요청 타임아웃 초 (기본 60)
    web_search : bool
        True 면 웹 검색 활성화 (KIK-686).
        - Gemini: Google Search Grounding(검색 결과 토큰은 입력 과금 대상 아님)
        - GPT/Grok: 현재 미지원(향후 Responses API 전환 시 대응 예정)
    reasoning : str, optional
        GPT 전용: 추론 깊이 제어 (KIK-686).
        "none" | "low" | "medium" | "high"
        None 이면 모델 기본값.

    Returns
    -------
    str or None
        응답 텍스트. API 키 미설정 또는 오류 시 None.
    """
    if provider not in _VALID_PROVIDERS:
        return None

    api_key = os.environ.get(_API_KEY_ENVS[provider])
    if not api_key:
        return None

    # 프로바이더별 파라미터 검증
    if web_search and provider != "gemini":
        print(f"[llm] WARN: web_search not supported for {provider}, ignoring", file=sys.stderr)
        web_search = False
    _VALID_REASONING = {"none", "low", "medium", "high"}
    if reasoning is not None and reasoning not in _VALID_REASONING:
        print(f"[llm] WARN: invalid reasoning '{reasoning}', using model default", file=sys.stderr)
        reasoning = None
    if reasoning is not None and provider != "gpt":
        reasoning = None  # GPT 외에는 조용히 무시

    t0 = time.time()
    try:
        if provider == "gemini":
            result = _call_gemini(api_key, model, prompt, system_prompt, timeout, web_search)
        elif provider == "gpt":
            result = _call_openai_compatible(
                api_key, _ENDPOINTS["gpt"], model, prompt, system_prompt, timeout,
                reasoning=reasoning,
            )
        elif provider == "grok":
            result = _call_openai_compatible(
                api_key, _ENDPOINTS["grok"], model, prompt, system_prompt, timeout,
            )
        else:
            return None
    except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
        elapsed = time.time() - t0
        # URL 에 포함된 API 키가 새지 않도록 오류 메시지 정제
        exc_str = str(exc)
        if "key=" in exc_str.lower() or "bearer" in exc_str.lower():
            exc_str = f"{type(exc).__name__} [details redacted]"
        print(
            f"[llm] FAIL {provider}/{model} ({elapsed:.1f}s): {exc_str}",
            file=sys.stderr,
        )
        return None

    elapsed = time.time() - t0
    length = len(result) if result else 0
    tags = []
    if web_search and provider == "gemini":
        tags.append("+grounding")
    if reasoning and provider == "gpt":
        tags.append(f"+reasoning={reasoning}")
    tag_str = "".join(tags)
    print(
        f"[llm] OK {provider}/{model}{tag_str} ({elapsed:.1f}s, {length} chars)",
        file=sys.stderr,
    )
    return result


def is_provider_available(provider: str) -> bool:
    """지정 프로바이더의 API 키가 설정되어 있는지."""
    env_var = _API_KEY_ENVS.get(provider)
    if not env_var:
        return False
    return bool(os.environ.get(env_var))


def get_available_providers() -> list[str]:
    """사용 가능한 프로바이더 목록을 반환한다."""
    return [p for p in _VALID_PROVIDERS if is_provider_available(p)]


# ---------------------------------------------------------------------------
# KIK-731: Gemini Deep Research re-export
# ---------------------------------------------------------------------------

try:
    from src.data.gemini_client import (  # noqa: E402
        gemini_deep_research,
        is_deep_research_enabled,
    )
    HAS_GEMINI_DR = True
except ImportError:
    HAS_GEMINI_DR = False


# ---------------------------------------------------------------------------
# 비공개 헬퍼
# ---------------------------------------------------------------------------

def _call_openai_compatible(
    api_key: str,
    endpoint: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    timeout: int,
    reasoning: Optional[str] = None,
) -> Optional[str]:
    """OpenAI 호환 API(GPT / Grok)를 호출한다."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {"model": model, "messages": messages}
    if reasoning is not None:
        payload["reasoning_effort"] = reasoning

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    timeout: int,
    web_search: bool = False,
) -> Optional[str]:
    """Google Gemini API 를 호출한다."""
    url = _ENDPOINTS["gemini"].format(model=model)

    payload: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    if web_search:
        payload["tools"] = [{"google_search": {}}]

    response = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    # Grounding 시 여러 parts 가 반환될 수 있음 — 텍스트 부분만 결합
    try:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        texts = [p.get("text", "") for p in parts if p.get("text")]
        return "\n".join(texts) if texts else None
    except (IndexError, TypeError):
        return None


__all__ = [
    "call_llm",
    "is_provider_available",
    "get_available_providers",
]
