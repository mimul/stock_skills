"""티커 심볼 유틸리티: 접미사 기반 통화·지역 추론.

지원 시장은 한국(KOSPI `.KS`, KOSDAQ `.KQ`)과 미국(접미사 없음) 두 곳뿐이다.
접미사 → 통화/지역 매핑의 단일 진실 공급원(SSoT).
"""

import re
from typing import Optional

from src.data.common import is_cash


# ---------------------------------------------------------------------------
# 심볼 탐지 패턴 (단일 진실 공급원)
# ---------------------------------------------------------------------------

# 한국 종목코드: 6자리 숫자 + .KS/.KQ (예: 005930.KS, 247540.KQ)
# 앞뒤에 영숫자가 붙어 있으면(1005930.KS, 005930.KSX) 종목코드로 보지 않는다.
_KR_CODE_RE = re.compile(
    r"(?<![0-9A-Za-z])(\d{6}\.K[SQ])(?![0-9A-Za-z])", re.IGNORECASE
)

# 현금 심볼: KRW.CASH / USD.CASH
_CASH_RE = re.compile(r"(?<![A-Za-z0-9.])([A-Z]{3}\.CASH)(?![A-Za-z0-9])")

# 미국 티커: 대문자 1~5자(+ 선택적 클래스 접미사 -B).
# - 앞: 영숫자·'.'·'^' 가 오면 안 된다 (7203.T 의 T, ^VIX 등 제외)
# - 뒤: 문장 끝, 비영숫자·비한글 문자, 문장 끝의 마침표, 또는 한국어 조사만 허용.
#   한국 회사명(SK하이닉스, LG에너지솔루션, KB금융, HD현대)처럼 영문 뒤에
#   한글 단어가 이어지면 티커가 아니라 회사명으로 본다.
_KO_PARTICLES = "은|는|이|가|을|를|의|와|과|도|로|에|만|랑|부터|까지"
_US_TICKER_RE = re.compile(
    r"(?<![A-Za-z0-9.^])([A-Z][A-Z0-9]{0,4}(?:-[A-Z])?)"
    r"(?=$|[^A-Za-z0-9가-힣.]|\.(?![A-Za-z])|(?:" + _KO_PARTICLES + r")(?![가-힣]))"
)

# 티커 형태이지만 티커가 아닌 영문 약어 (금융 용어·지수·통화·한국 그룹명 등).
# 여기에 걸리면 심볼 추출을 건너뛰고 회사명 조회로 넘어간다.
NON_TICKER_WORDS: frozenset[str] = frozenset({
    # 금융 지표·용어
    "ETF", "ETN", "ISA", "IRP", "PER", "PBR", "PSR", "PEG", "EPS", "BPS",
    "DPS", "ROE", "ROA", "ROIC", "EV", "PF", "NAV", "MDD", "ADR", "REIT",
    "IPO", "ESG", "M&A", "CEO", "CFO", "IR", "PR", "R&D", "YTD", "YOY",
    "QOQ", "MOM", "FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2", "RSI", "MACD",
    "SMA", "EMA", "OBV", "ATH", "ATL", "OTC", "GDP", "CPI", "PPI", "FOMC",
    "FED", "FX", "KIS", "DART", "HTS", "MTS", "CASH",
    # 통화·지수·시장
    "KRW", "USD", "JPY", "EUR", "CNY", "VIX", "KOSPI", "KRX", "NYSE", "US",
    "KR", "KS", "KQ", "USA",
    # 일반 약어
    "AI", "IT", "OK", "TV", "PC", "SNS", "API", "LLM", "PDF", "CSV", "JSON",
    "ETC", "VS", "AND", "OR", "THE", "NO", "YES", "TODO", "DIY", "MOU",
    # 영문 표기가 흔한 한국 그룹/회사명 (미국 티커와 겹치지 않는 것만)
    "SK", "LG", "NAVER", "HMM", "POSCO", "CJ", "LS", "NH", "HL", "DL", "LX",
    "KCC", "BGF", "JYP", "OCI", "SKC",
})

# 하위 호환용 통합 패턴 (findall 기반 외부 사용처를 위해 유지)
SYMBOL_PATTERN = re.compile(
    r"(\d{6}\.K[SQ]|[A-Z]{3}\.CASH|[A-Z][A-Z0-9]{0,4})"
)


def _iter_symbols(text: str):
    """텍스트에 등장하는 유효 심볼을 (위치, 심볼) 순서로 생성한다."""
    if not text:
        return
    for m in _KR_CODE_RE.finditer(text):
        yield m.start(), m.group(1).upper()
    for m in _CASH_RE.finditer(text):
        yield m.start(), m.group(1)
    for m in _US_TICKER_RE.finditer(text):
        token = m.group(1)
        if token in NON_TICKER_WORDS:
            continue
        yield m.start(), token


def extract_symbol(text: str) -> Optional[str]:
    """텍스트에서 티커 심볼 하나를 추출한다 (예: 005930.KS, AAPL).

    한국 종목코드가 하나라도 있으면 위치와 무관하게 그것을 우선한다.
    영문 토큰은 한국 회사명 접두(SK하이닉스 등)와 혼동되기 쉽기 때문이다.
    그다음 현금 심볼, 미국 티커 순으로 가장 앞에 나온 것을 돌려준다.
    """
    kr = _KR_CODE_RE.search(text or "")
    if kr:
        return kr.group(1).upper()
    candidates = sorted(_iter_symbols(text))
    return candidates[0][1] if candidates else None


def extract_all_symbols(text: str) -> list[str]:
    """텍스트에서 중복 없이 모든 티커 심볼을 등장 순서대로 추출한다."""
    seen: set[str] = set()
    result: list[str] = []
    for _, sym in sorted(_iter_symbols(text)):
        if sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


# ---------------------------------------------------------------------------
# 접미사 매핑
# ---------------------------------------------------------------------------

SUFFIX_TO_REGION = {
    ".KS": "South Korea",
    ".KQ": "South Korea",
}

# 하위 호환 별칭 (KIK-392)
SUFFIX_TO_COUNTRY = SUFFIX_TO_REGION

SUFFIX_TO_CURRENCY = {
    ".KS": "KRW",
    ".KQ": "KRW",
}

# 접미사 → 소문자 지역 코드 (KIK-438)
SUFFIX_TO_REGION_CODE = {
    ".KS": "kr",
    ".KQ": "kr",
}

# 접미사 → 매매 단위. 한국·미국 모두 1주 단위로 거래한다.
SUFFIX_TO_LOT_SIZE: dict[str, int] = {
    ".KS": 1,
    ".KQ": 1,
}

_CURRENCY_TO_REGION_CODE = {"KRW": "kr", "USD": "us"}
_CURRENCY_TO_COUNTRY = {"KRW": "South Korea", "USD": "United States"}


def _suffix_of(symbol: str) -> Optional[str]:
    """심볼에서 알려진 접미사를 찾아 반환한다. 없으면 None."""
    upper = symbol.upper()
    for suffix in SUFFIX_TO_CURRENCY:
        if upper.endswith(suffix):
            return suffix
    return None


def is_korean_stock(symbol: str) -> bool:
    """한국 상장 종목(.KS/.KQ)인지 여부."""
    return _suffix_of(symbol) is not None


def get_lot_size(symbol: str) -> int:
    """심볼의 최소 매매 단위를 반환한다.

    한국·미국 모두 1주 단위이므로 항상 1을 반환한다.
    API 호환을 위해 함수는 유지한다.
    """
    if is_cash(symbol):
        return 1
    suffix = _suffix_of(symbol)
    if suffix is not None:
        return SUFFIX_TO_LOT_SIZE[suffix]
    return 1


def lot_cost(symbol: str, price: float) -> float:
    """1단위(최소 매매 단위) 매수에 필요한 금액.

    예: 005930.KS 가 72,000원이면 1 * 72000 = 72,000원
    """
    return get_lot_size(symbol) * price


def round_to_lot_size(shares: int, symbol: str) -> int:
    """주식 수를 매매 단위의 배수로 반올림한다.

    매매 단위가 1이면 그대로 반환한다. 파이썬 내장 round()(은행가 반올림)를 사용한다.
    """
    lot = get_lot_size(symbol)
    if lot <= 1:
        return shares
    return round(shares / lot) * lot


def validate_lot_size(shares: int, symbol: str) -> None:
    """주식 수가 매매 단위의 배수인지 검증한다.

    매매 단위가 1보다 큰 시장에서만 ValueError 를 발생시킨다.
    한국·미국은 1주 단위이므로 항상 통과한다.
    """
    lot = get_lot_size(symbol)
    if lot <= 1:
        return
    if shares % lot != 0:
        nearest = round_to_lot_size(shares, symbol)
        raise ValueError(
            f"{symbol}은(는) {lot}주 단위로 매매해야 합니다. "
            f"{shares}주는 유효하지 않습니다 (가장 가까운 유효 수량: {nearest}주)"
        )


def cash_currency(symbol: str) -> str:
    """현금 심볼에서 통화를 추출한다 (예: 'KRW.CASH' -> 'KRW')."""
    return symbol.upper().replace(".CASH", "")


def infer_currency(symbol: str, info: dict | None = None) -> str:
    """티커 접미사로 통화를 추론한다.

    *info* 에 'currency' 키가 있으면 그 값을 우선 사용한다.
    접미사가 없으면 미국 주식으로 보고 USD 를 반환한다.
    """
    if info is not None:
        currency_from_info = info.get("currency")
        if currency_from_info:
            return currency_from_info
    if is_cash(symbol):
        return cash_currency(symbol)
    suffix = _suffix_of(symbol)
    if suffix is not None:
        return SUFFIX_TO_CURRENCY[suffix]
    return "USD"


def infer_region_code(symbol: str) -> str:
    """티커 접미사로 소문자 지역 코드를 추론한다 (KIK-438).

    반환값은 "kr" 또는 "us".
    """
    if is_cash(symbol):
        return _CURRENCY_TO_REGION_CODE.get(cash_currency(symbol), "us")
    suffix = _suffix_of(symbol)
    if suffix is not None:
        return SUFFIX_TO_REGION_CODE[suffix]
    return "us"


def infer_country(symbol: str, info: dict | None = None) -> str:
    """티커 접미사로 국가/지역명을 추론한다.

    *info* 에 'country' 또는 'region' 키가 있으면 그 값을 우선 사용한다.
    접미사가 없으면 미국 주식으로 본다.
    """
    if info is not None:
        country_from_info = info.get("country") or info.get("region")
        if country_from_info:
            return country_from_info
    if is_cash(symbol):
        return _CURRENCY_TO_COUNTRY.get(cash_currency(symbol), "Unknown")
    suffix = _suffix_of(symbol)
    if suffix is not None:
        return SUFFIX_TO_REGION[suffix]
    return "United States"
