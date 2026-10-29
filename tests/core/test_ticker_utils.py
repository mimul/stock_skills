"""src.data.ticker_utils 테스트 (KIK-473, KIK-597, 한국 시장 전환)."""

import pytest

from src.data import ticker_utils
from src.data.ticker_utils import (
    extract_all_symbols,
    extract_symbol,
    get_lot_size,
    infer_country,
    infer_currency,
    infer_region_code,
    is_korean_stock,
    lot_cost,
    round_to_lot_size,
    validate_lot_size,
)


class TestExtractSymbol:
    def test_korean_six_digit_code_is_kept_whole(self):
        # 기존 4자리 패턴은 005930.KS 를 5930.KS 로 잘라내는 버그가 있었다
        assert extract_symbol("삼성전자 005930.KS 분석해줘") == "005930.KS"

    def test_kosdaq_code(self):
        assert extract_symbol("247540.KQ 어때?") == "247540.KQ"

    def test_us_ticker(self):
        assert extract_symbol("AAPL 어때?") == "AAPL"

    def test_cash_symbol(self):
        assert extract_symbol("KRW.CASH 잔고") == "KRW.CASH"

    def test_no_symbol(self):
        assert extract_symbol("오늘은 매매 안 함") is None


class TestExtractAllSymbols:
    def test_single_symbol(self):
        assert extract_all_symbols("NVDA가 급등했다") == ["NVDA"]

    def test_multiple_symbols(self):
        result = extract_all_symbols("NVDA와 AAPL이 올랐다. 005930.KS는 하락")
        assert set(result) == {"NVDA", "AAPL", "005930.KS"}

    def test_no_symbols(self):
        assert extract_all_symbols("오늘은 매매하지 않는다") == []

    def test_duplicate_removal(self):
        assert extract_all_symbols("NVDA 상승. NVDA 실적도 좋다") == ["NVDA"]

    def test_kospi_and_kosdaq(self):
        result = extract_all_symbols("000660.KS와 196170.KQ를 샀다")
        assert set(result) == {"000660.KS", "196170.KQ"}

    def test_empty_string(self):
        assert extract_all_symbols("") == []


class TestIsKoreanStock:
    def test_kospi(self):
        assert is_korean_stock("005930.KS") is True

    def test_kosdaq_lowercase(self):
        assert is_korean_stock("247540.kq") is True

    def test_us(self):
        assert is_korean_stock("AAPL") is False


# ===================================================================
# 매매 단위 (한국·미국 모두 1주)
# ===================================================================


class TestLotSize:
    def test_korean_stock_lot_is_one(self):
        assert get_lot_size("005930.KS") == 1
        assert get_lot_size("247540.KQ") == 1

    def test_us_stock_lot_is_one(self):
        assert get_lot_size("AAPL") == 1

    def test_cash_lot_is_one(self):
        assert get_lot_size("KRW.CASH") == 1

    def test_lot_cost_equals_price(self):
        assert lot_cost("005930.KS", 72000) == 72000


class TestRoundToLotSize:
    def test_korean_stock_passthrough(self):
        assert round_to_lot_size(149, "005930.KS") == 149

    def test_us_stock_passthrough(self):
        assert round_to_lot_size(17, "AAPL") == 17

    def test_zero_shares(self):
        assert round_to_lot_size(0, "005930.KS") == 0

    def test_cash_symbol(self):
        assert round_to_lot_size(50, "KRW.CASH") == 50


class TestValidateLotSize:
    def test_korean_stock_any_amount_passes(self):
        validate_lot_size(1, "005930.KS")
        validate_lot_size(7, "247540.KQ")

    def test_us_stock_any_amount_passes(self):
        validate_lot_size(1, "AAPL")
        validate_lot_size(7, "MSFT")

    def test_cash_symbol_passes(self):
        validate_lot_size(50, "KRW.CASH")


# ===================================================================
# 통화·지역 추론
# ===================================================================


class TestInferCurrency:
    def test_korean_stock(self):
        assert infer_currency("005930.KS") == "KRW"
        assert infer_currency("247540.KQ") == "KRW"

    def test_us_stock(self):
        assert infer_currency("AAPL") == "USD"

    def test_cash(self):
        assert infer_currency("USD.CASH") == "USD"
        assert infer_currency("KRW.CASH") == "KRW"

    def test_info_overrides(self):
        assert infer_currency("AAPL", {"currency": "KRW"}) == "KRW"


class TestInferRegionCode:
    def test_korean(self):
        assert infer_region_code("005930.KS") == "kr"
        assert infer_region_code("247540.KQ") == "kr"

    def test_us(self):
        assert infer_region_code("AAPL") == "us"

    def test_cash(self):
        assert infer_region_code("KRW.CASH") == "kr"
        assert infer_region_code("USD.CASH") == "us"


class TestInferCountry:
    def test_korean(self):
        assert infer_country("005930.KS") == "South Korea"

    def test_us(self):
        assert infer_country("AAPL") == "United States"

    def test_cash(self):
        assert infer_country("KRW.CASH") == "South Korea"
        assert infer_country("USD.CASH") == "United States"

    def test_info_overrides(self):
        assert infer_country("AAPL", {"country": "Canada"}) == "Canada"


# ===================================================================
# 한국 회사명 영문 접두·경계 조건 (코드 리뷰 H1/L1)
# ===================================================================


class TestKoreanCompanyNamePrefix:
    """SK하이닉스·LG에너지솔루션처럼 영문으로 시작하는 한국 회사명은 티커가 아니다."""

    @pytest.mark.parametrize("text", [
        "SK하이닉스 어때?",
        "LG에너지솔루션 분석",
        "KB금융 매수 이유",
        "HD현대중공업 전망",
        "CJ제일제당 실적",
        "NAVER 분석해줘",
        "HMM 주가",
    ])
    def test_company_name_prefix_is_not_a_symbol(self, text):
        assert extract_symbol(text) is None
        assert extract_all_symbols(text) == []

    def test_korean_code_beats_leading_english(self):
        assert extract_symbol("SK하이닉스(000660.KS) 어때?") == "000660.KS"

    def test_us_ticker_followed_by_particle(self):
        assert extract_symbol("NVDA는 어때?") == "NVDA"
        assert extract_symbol("AAPL을 샀다") == "AAPL"

    def test_class_share_ticker(self):
        assert extract_symbol("BRK-B 어때") == "BRK-B"

    def test_sentence_end_period(self):
        assert extract_symbol("AAPL.") == "AAPL"


class TestNonTickerWords:
    @pytest.mark.parametrize("text", [
        "ETF 추천해줘", "PF 괜찮아?", "PER 낮은 종목", "VIX 추이", "KOSPI 전망",
        "AI 테마", "^VIX 추이",
    ])
    def test_financial_abbreviations_are_ignored(self, text):
        assert extract_symbol(text) is None


class TestSymbolBoundaries:
    @pytest.mark.parametrize("text", ["1005930.KS", "005930.KSX", "0059301.KS"])
    def test_malformed_korean_code_rejected(self, text):
        assert extract_symbol(text) is None

    def test_lowercase_suffix_normalized(self):
        assert extract_symbol("005930.ks 분석") == "005930.KS"

    def test_unsupported_foreign_suffix_rejected(self):
        assert extract_symbol("7203.T 어때?") is None
        assert extract_symbol("D05.SI 상황은?") is None

    def test_all_symbols_keep_order(self):
        assert extract_all_symbols("MSFT, AAPL 비교") == ["MSFT", "AAPL"]


# ===================================================================
# 매매 단위 > 1 분기 (monkeypatch, 코드 리뷰 M8)
# ===================================================================


class TestLotSizeGreaterThanOne:
    @pytest.fixture(autouse=True)
    def _lot_100(self, monkeypatch):
        monkeypatch.setitem(ticker_utils.SUFFIX_TO_LOT_SIZE, ".KS", 100)

    def test_get_lot_size(self):
        assert get_lot_size("005930.KS") == 100

    def test_lot_cost(self):
        assert lot_cost("005930.KS", 72000) == 7_200_000

    def test_round_to_lot_size(self):
        assert round_to_lot_size(149, "005930.KS") == 100
        assert round_to_lot_size(151, "005930.KS") == 200
        assert round_to_lot_size(0, "005930.KS") == 0

    def test_validate_lot_size_passes_on_multiple(self):
        validate_lot_size(200, "005930.KS")

    def test_validate_lot_size_raises_with_nearest(self):
        with pytest.raises(ValueError, match="100주 단위") as exc:
            validate_lot_size(149, "005930.KS")
        assert "100주" in str(exc.value)

    def test_other_suffix_unaffected(self):
        assert get_lot_size("247540.KQ") == 1
        validate_lot_size(7, "247540.KQ")
