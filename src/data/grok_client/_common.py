"""grok_client 패키지 공용 API 호출 헬퍼·상수·에러 상태.

KIK-508 서브모듈 분할 시 grok_client.py 에서 추출.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from src.data.ticker_utils import is_korean_stock

# 프로젝트 루트의 .env 로드
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


_API_URL = "https://api.x.ai/v1/responses"
_DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
_error_warned = [False]

# ---------------------------------------------------------------------------
# 에러 상태 추적 (KIK-431)
# ---------------------------------------------------------------------------

_error_state: dict = {
    "status": "ok",       # not_configured | ok | auth_error | rate_limited | timeout | other_error
    "status_code": None,  # int | None
    "message": "",
}


def get_error_status() -> dict:
    """현재 Grok API 에러 상태를 반환한다 (KIK-431)."""
    return dict(_error_state)


def reset_error_state() -> None:
    """에러 상태를 'ok' 로 초기화한다 (KIK-431)."""
    _error_state["status"] = "ok"
    _error_state["status_code"] = None
    _error_state["message"] = ""


# ---------------------------------------------------------------------------
# 빈 결과 상수
# ---------------------------------------------------------------------------

EMPTY_STOCK_DEEP = {
    "recent_news": [],
    "catalysts": {"positive": [], "negative": []},
    "analyst_views": [],
    "x_sentiment": {"score": 0.0, "summary": "", "key_opinions": []},
    "competitive_notes": [],
    "raw_response": "",
}

EMPTY_INDUSTRY = {
    "trends": [],
    "key_players": [],
    "growth_drivers": [],
    "risks": [],
    "regulatory": [],
    "investor_focus": [],
    "raw_response": "",
}

EMPTY_MARKET = {
    "price_action": "",
    "macro_factors": [],
    "sentiment": {"score": 0.0, "summary": ""},
    "upcoming_events": [],
    "sector_rotation": [],
    "raw_response": "",
}

EMPTY_TRENDING = {
    "stocks": [],
    "market_context": "",
    "raw_response": "",
}

EMPTY_BUSINESS = {
    "overview": "",
    "segments": [],
    "revenue_model": "",
    "competitive_advantages": [],
    "key_metrics": [],
    "growth_strategy": [],
    "risks": [],
    "raw_response": "",
}

EMPTY_TRENDING_THEMES = {
    "themes": [],
    "raw_response": "",
}


# ---------------------------------------------------------------------------
# 공개 헬퍼
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Grok API 사용 가능 여부 (XAI_API_KEY 설정 여부)."""
    return bool(os.environ.get("XAI_API_KEY"))


# ---------------------------------------------------------------------------
# 비공개 헬퍼
# ---------------------------------------------------------------------------

_FALLBACK_NOTE = "    → yfinance 데이터만으로 실행합니다"


def _get_api_key() -> Optional[str]:
    """API 키 또는 None 을 반환한다."""
    return os.environ.get("XAI_API_KEY")


def _is_korean_stock(symbol: str) -> bool:
    """*symbol* 이 한국 상장 종목(.KS/.KQ)이면 True (ticker_utils 에 위임)."""
    return is_korean_stock(symbol)


def _contains_korean(text: str) -> bool:
    """*text* 에 한글(완성형·자모·호환 자모)이 포함되면 True."""
    return any(
        0xAC00 <= ord(c) <= 0xD7A3
        or 0x1100 <= ord(c) <= 0x11FF
        or 0x3130 <= ord(c) <= 0x318F
        for c in text
    )


def _warn_once(message: str) -> None:
    """최초 1회만 stderr 에 경고를 출력한다."""
    if not _error_warned[0]:
        print(message, file=sys.stderr)
        _error_warned[0] = True


def _set_error(status: str, status_code: Optional[int], message: str) -> None:
    _error_state["status"] = status
    _error_state["status_code"] = status_code
    _error_state["message"] = message


def _http_error_message(status_code: int) -> str:
    """HTTP 상태 코드별 사용자 안내 메시지."""
    if status_code == 401:
        return (
            "⚠️  Grok API 인증 오류\n"
            "    원인: API 키가 유효하지 않거나 만료되었을 수 있습니다\n"
            "    대처: xai.com 에서 API 키를 확인·재발급하세요\n"
            f"{_FALLBACK_NOTE}"
        )
    if status_code == 429:
        return (
            "⚠️  Grok API 요청 한도에 도달했습니다\n"
            "    원인: 짧은 시간에 너무 많은 요청이 전송되었습니다\n"
            "    대처: 잠시 후(보통 1~2분) 다시 시도하세요\n"
            f"{_FALLBACK_NOTE}"
        )
    return (
        f"⚠️  Grok API 오류 (HTTP {status_code})\n"
        "    대처: 잠시 후 다시 시도하세요\n"
        f"{_FALLBACK_NOTE}"
    )


def _call_grok_api(prompt: str, timeout: int = 30, use_tools: bool = True) -> str:
    """Grok API 공통 요청 헬퍼.

    Parameters
    ----------
    prompt : str
        API 에 보낼 프롬프트.
    timeout : int
        요청 타임아웃(초).
    use_tools : bool
        True(기본)면 x_search / web_search 툴을 붙인다.
        실시간 검색 없이 순수 텍스트 합성만 할 때는 False (KIK-452).

    Returns
    -------
    str
        응답의 텍스트 부분. 오류 시 빈 문자열.
    """
    api_key = _get_api_key()
    if not api_key:
        _warn_once(
            "⚠️  Grok API 키가 설정되어 있지 않습니다\n"
            "    원인: XAI_API_KEY 환경 변수가 설정되지 않았습니다\n"
            "    대처: export XAI_API_KEY=your_key 를 설정하세요\n"
            f"{_FALLBACK_NOTE}"
        )
        _set_error("not_configured", None, "XAI_API_KEY is not set")
        return ""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": _DEFAULT_MODEL,
            "input": prompt,
        }
        if use_tools:
            payload["tools"] = [{"type": "x_search"}, {"type": "web_search"}]

        response = requests.post(
            _API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if response.status_code != 200:
            _warn_once(_http_error_message(response.status_code))
            # KIK-431: 상태 코드별 에러 유형 기록
            if response.status_code == 401:
                status = "auth_error"
            elif response.status_code == 429:
                status = "rate_limited"
            else:
                status = "other_error"
            _set_error(status, response.status_code, f"HTTP {response.status_code}")
            return ""

        data = response.json()

        # 응답에서 텍스트 내용 추출
        raw_text = ""
        output_items = data.get("output", [])
        for item in output_items:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        raw_text = content.get("text", "")
                        break

        _set_error("ok", 200, "")
        return raw_text

    except requests.exceptions.Timeout:
        _warn_once(
            "⚠️  Grok API 연결이 타임아웃되었습니다\n"
            "    원인: 네트워크가 불안정하거나 API 가 일시적으로 응답하지 않습니다\n"
            "    대처: 네트워크 연결을 확인한 뒤 다시 시도하세요\n"
            f"{_FALLBACK_NOTE}"
        )
        _set_error("timeout", None, "Request timed out")
        return ""
    except requests.exceptions.RequestException as e:
        _warn_once(
            "⚠️  Grok API 연결에 실패했습니다\n"
            "    원인: 네트워크 오류가 발생했습니다\n"
            "    대처: 네트워크 연결을 확인한 뒤 다시 시도하세요\n"
            f"{_FALLBACK_NOTE}"
        )
        _set_error("other_error", None, str(e))
        return ""
    except Exception as e:
        _warn_once(
            "⚠️  Grok API 에서 예기치 않은 오류가 발생했습니다\n"
            "    대처: 잠시 후 다시 시도하세요\n"
            f"{_FALLBACK_NOTE}"
        )
        _set_error("other_error", None, str(e))
        return ""


def _parse_json_response(raw_text: str) -> dict:
    """*raw_text* 에서 JSON 객체를 추출한다.

    첫 ``{`` 와 마지막 ``}`` 사이를 ``json.loads`` 로 파싱한다.
    실패 시 빈 dict 를 반환한다.
    """
    try:
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(raw_text[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def _parse_json_array_response(raw_text: str):
    """*raw_text* 에서 JSON 배열을 추출한다.

    첫 ``[`` 와 마지막 ``]`` 사이를 ``json.loads`` 로 파싱한다.
    실패 시 빈 list 를 반환한다.
    """
    try:
        json_start = raw_text.find("[")
        json_end = raw_text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(raw_text[json_start:json_end])
            if isinstance(result, list):
                return result
    except (json.JSONDecodeError, ValueError):
        pass
    return []
