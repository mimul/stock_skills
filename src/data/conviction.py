"""conviction(매도 금지) 판정 키워드의 단일 진실 공급원(SSoT).

`preflight.extract_convictions` 와 `context.fallback_context._detect_conviction`
이 같은 규칙을 공유하도록 여기에 모은다.

판정은 공백을 제거한 소문자 본문에 대해 부분 문자열 매칭으로 한다.
"매도 금지"/"매도금지", "안 팔"/"안팔" 처럼 띄어쓰기 변형을 모두 잡기 위함이다.
"""

from __future__ import annotations

import re

# 공백 제거·소문자 기준 키워드. 새 키워드를 추가할 때는 띄어쓰기 없이 적는다.
CONVICTION_KEYWORDS: tuple[str, ...] = (
    "홀드확정",
    "안팜",
    "안팔",
    "안판다",  # "안 판다" (ㄹ 탈락 활용). "안판"은 "불안 판단" 류 오탐이 있어 쓰지 않는다
    "팔지않",
    "매도금지",
    "보유확정",
    "conviction",
)

_WHITESPACE = re.compile(r"\s+")


def _compact(text: str) -> str:
    """소문자화 후 공백을 모두 제거한다."""
    return _WHITESPACE.sub("", (text or "").lower())


def is_conviction_text(content: str, source: str = "") -> bool:
    """메모 본문/출처가 conviction(매도 금지) 신호인지 판정한다.

    - 본문: 공백을 제거한 소문자 본문에 CONVICTION_KEYWORDS 중 하나가 포함
    - 출처: ``user-conviction`` 으로 시작
    """
    if (source or "").lower().startswith("user-conviction"):
        return True
    compact = _compact(content)
    return any(k in compact for k in CONVICTION_KEYWORDS)
