# 데이터 모델 정의 (KIK-524)

`yahoo_client` 가 반환하는 2종류의 dict 스키마. 스크리너·리포트·헬스체크 등 모든 코어 모듈이 이 구조에 의존한다.

---

## stock_info dict（27 필드）

`yahoo_client.get_stock_info(symbol)` 이 반환하는 기본 데이터. JSON 캐시 대상.

| 키 | 타입 | 설명 | yfinance 원본 키 | 정규화 |
|:---|:---|:---|:---|:---|
| `symbol` | `str` | 티커 심볼（예: `005930.KS`, `AAPL`） | 인자 | — |
| `name` | `str \| None` | 기업명 | `shortName` / `longName` | — |
| `sector` | `str \| None` | 섹터 | `sector` | — |
| `industry` | `str \| None` | 업종 | `industry` | — |
| `currency` | `str \| None` | 통화 코드 (KRW/USD) | `currency` | — |
| `price` | `float \| None` | 현재 주가 | `regularMarketPrice` | — |
| `market_cap` | `float \| None` | 시가총액 | `marketCap` | — |
| `per` | `float \| None` | PER（주가수익비율） | `trailingPE` | — |
| `forward_per` | `float \| None` | 예상 PER | `forwardPE` | — |
| `pbr` | `float \| None` | PBR（주가순자산비율） | `priceToBook` | — |
| `psr` | `float \| None` | PSR（주가매출비율） | `priceToSalesTrailing12Months` | — |
| `roe` | `float \| None` | ROE（자기자본이익률）. 비율 (0.12 = 12%) | `returnOnEquity` | — |
| `roa` | `float \| None` | ROA（총자산이익률）. 비율 | `returnOnAssets` | — |
| `profit_margin` | `float \| None` | 순이익률. 비율 | `profitMargins` | — |
| `operating_margin` | `float \| None` | 영업이익률. 비율 | `operatingMargins` | — |
| `dividend_yield` | `float \| None` | 배당수익률（예상）. 비율 (0.028 = 2.8%) | `dividendYield` | `_normalize_ratio` |
| `dividend_yield_trailing` | `float \| None` | 배당수익률（실적）. 비율 | `trailingAnnualDividendYield` | — |
| `payout_ratio` | `float \| None` | 배당성향. 비율 | `payoutRatio` | — |
| `revenue_growth` | `float \| None` | 매출 성장률. 비율 (0.15 = 15%) | `revenueGrowth` | — |
| `earnings_growth` | `float \| None` | 이익 성장률. 비율 | `earningsGrowth` | — |
| `debt_to_equity` | `float \| None` | D/E 비율（백분율, 105.0 = 105%） | `debtToEquity` | — |
| `current_ratio` | `float \| None` | 유동비율 | `currentRatio` | — |
| `free_cashflow` | `float \| None` | 잉여현금흐름（절대값） | `freeCashflow` | — |
| `beta` | `float \| None` | 베타값 | `beta` | — |
| `fifty_two_week_high` | `float \| None` | 52주 고가 | `fiftyTwoWeekHigh` | — |
| `fifty_two_week_low` | `float \| None` | 52주 저가 | `fiftyTwoWeekLow` | — |
| `quoteType` | `str \| None` | 종별 ("EQUITY" / "ETF" 등) | `quoteType` | — |

**합계: 27 키**（`quoteType` 은 KIK-469 에서 추가）

### 정규화 규칙 (`_normalize_ratio`)

yfinance 는 `dividendYield` 를 퍼센트 값（예: 2.52）으로 반환한다. `_normalize_ratio()` 는 항상 100 으로 나누어 비율로 변환한다.

```python
def _normalize_ratio(value):
    if value is None:
        return None
    return value / 100.0  # 2.52 → 0.0252
```

`dividend_yield_trailing`（`trailingAnnualDividendYield`）은 yfinance 가 비율로 반환하므로 정규화 불필요.

### 이상값 정리 (`_sanitize_anomalies`)

| 필드 | 조건 | 처리 |
|:---|:---|:---|
| `dividend_yield` | > 0.15 (15%) | → `None` |
| `dividend_yield_trailing` | > 0.15 (15%) | → `None` |
| `pbr` | < 0.05 | → `None` |
| `per` | 0 < per < 1.0 | → `None` |
| `roe` | < -1.0 or > 2.0 | → `None` |

### 별칭 대응

yfinance 원본 키와 정규화 키의 대응표:

| 정규화 키 | yfinance 원본 키 |
|:---|:---|
| `per` | `trailingPE` |
| `pbr` | `priceToBook` |
| `dividend_yield` | `dividendYield` |
| `roe` | `returnOnEquity` |
| `revenue_growth` | `revenueGrowth` |

---

## stock_detail dict（45+ 필드）

`yahoo_client.get_stock_detail(symbol)` 이 반환하는 상세 데이터. `stock_info` 의 모든 필드를 포함하고 재무제표 데이터를 추가한다.

### stock_info 에서 상속（27 필드）

위 `stock_info dict` 의 모든 키가 그대로 포함된다.

### 추가 필드: 가격

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `price_history` | `list[float] \| None` | 2년치 종가 리스트（시계열 순） | `ticker.history(period="2y")` |

### 추가 필드: 재무상태표

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `equity_ratio` | `float \| None` | 자기자본비율（순자산/총자산） | `balance_sheet` |
| `total_assets` | `float \| None` | 총자산 | `balance_sheet` |
| `equity_history` | `list[float]` | 순자산 추이（최신→과거, 최대 4기） | `balance_sheet` |

### 추가 필드: 현금흐름

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `operating_cashflow` | `float \| None` | 영업 CF | `cashflow` |
| `fcf` | `float \| None` | 잉여 CF | `cashflow` |
| `dividend_paid` | `float \| None` | 배당금 지급（음수=지출） | `cashflow` (KIK-375) |
| `stock_repurchase` | `float \| None` | 자사주 매입（음수=지출） | `cashflow` (KIK-375) |
| `dividend_paid_history` | `list[float]` | 배당금 지급 추이（최신→과거, 최대 4기） | `cashflow` (KIK-380) |
| `stock_repurchase_history` | `list[float]` | 자사주 매입 추이（최신→과거, 최대 4기） | `cashflow` (KIK-380) |
| `cashflow_fiscal_years` | `list[int]` | 각 기의 회계연도（예: [2025, 2024, 2023]） | `cashflow` (KIK-380) |

### 추가 필드: 손익계산서

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `net_income_stmt` | `float \| None` | 당기순이익 | `income_stmt` |
| `eps_current` | `float \| None` | 희석 EPS（최신기） | `income_stmt` |
| `eps_previous` | `float \| None` | 희석 EPS（전기） | `income_stmt` |
| `eps_growth` | `float \| None` | EPS 성장률. 비율 (0.094 = 9.4%) | 산출 |
| `revenue_history` | `list[float]` | 매출 추이（최신→과거, 최대 4기） | `income_stmt` |
| `net_income_history` | `list[float]` | 순이익 추이（최신→과거, 최대 4기） | `income_stmt` |

### 추가 필드: 부채·평가

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `total_debt` | `float \| None` | 이자부채 합계 | `ticker.info` |
| `ebitda` | `float \| None` | EBITDA | `ticker.info` |

### 추가 필드: 애널리스트 (KIK-359)

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `target_high_price` | `float \| None` | 애널리스트 목표 주가（상한） | `ticker.info` |
| `target_low_price` | `float \| None` | 애널리스트 목표 주가（하한） | `ticker.info` |
| `target_mean_price` | `float \| None` | 애널리스트 목표 주가（평균） | `ticker.info` |
| `number_of_analyst_opinions` | `int \| None` | 애널리스트 수 | `ticker.info` |
| `recommendation_mean` | `float \| None` | 추천 평균값（1=Strong Buy ~ 5=Strong Sell） | `ticker.info` |
| `forward_eps` | `float \| None` | 예상 EPS | `ticker.info` |

### 추가 필드: ETF (KIK-469)

ETF 인 경우에만 유의미한 값을 가진다. 개별주에서는 `None` 이 많다. 코스닥 소형주는 재무 데이터 자체가 누락되는 경우가 있으므로 `None` 처리를 전제로 한다.

| 키 | 타입 | 설명 | 소스 |
|:---|:---|:---|:---|
| `expense_ratio` | `float \| None` | 보수율 | `ticker.info` (`annualReportExpenseRatio`) |
| `total_assets_fund` | `float \| None` | AUM（운용자산 잔고） | `ticker.info` (`totalAssets`) |
| `fund_category` | `str \| None` | 펀드 카테고리 | `ticker.info` (`category`) |
| `fund_family` | `str \| None` | 펀드 패밀리 | `ticker.info` (`fundFamily`) |

---

## portfolio.csv（12 컬럼）

`src/data/portfolio_io.py` 가 읽고 쓰는 보유 종목 데이터.

| 컬럼 | 타입 | 설명 |
|:---|:---|:---|
| `symbol` | str | 티커 심볼（005930.KS, 247540.KQ, AAPL 등） |
| `shares` | int | 보유 주수（한국·미국 모두 1주 단위） |
| `cost_price` | float | 평균 취득 단가 |
| `cost_currency` | str | 취득 통화（KRW, USD. 기본값 KRW） |
| `purchase_date` | str | 취득일（YYYY-MM-DD） |
| `memo` | str | 메모 |
| `next_earnings` | str | 직근 실적 발표일（YYYY-MM-DD）. ETF 는 공란 (KIK-683) |
| `div_yield` | float? | 배당수익률（%）. None = 미설정 (KIK-694) |
| `buyback_yield` | float? | 자사주 매입 수익률（%）(KIK-694) |
| `total_return` | float? | 총환원율（%）= div_yield + buyback_yield (KIK-694) |
| `beta` | float? | 베타값 (KIK-694) |
| `role` | str | PF 내 역할（장기인컴/성장/헤지）(KIK-694) |

**갱신 빈도**: div_yield 는 분기 실적 후, buyback_yield 는 연 1회 또는 발표 시, beta 는 월 1회, role 은 변경 시에만.

## cash_balance.json

`src/data/portfolio_io.py` 의 `load_cash_balance()` / `load_total_assets()` 가 읽는 현금 잔고 (KIK-742 계층 형식 SSoT).

```json
{
  "date": "YYYY-MM-DD",
  "timestamp": "ISO-8601",
  "total_krw": 10000000,
  "breakdown": {
    "KRW": {"amount": 7200000},
    "USD": {"amount": 2000.0, "krw_equivalent": 2800000, "rate_krw_per_usd": 1400.0}
  },
  "changelog": ["..."]
}
```

| 키 | 타입 | 설명 |
|:---|:---|:---|
| `total_krw` | int/float | 전체 현금의 원화 환산 합계 |
| `breakdown.KRW.amount` | int/float | 원화 잔고 |
| `breakdown.USD.amount` | float | 달러 잔고 |
| `breakdown.USD.krw_equivalent` | int/float | 달러 잔고의 원화 환산액 |
| `breakdown.USD.rate_krw_per_usd` | float | 환산에 사용한 USD/KRW 환율 |

`load_total_assets()` 의 반환 키는 `{positions, cash, cash_krw, has_cash}` 다.

---

## 공통 유틸리티

### `finite_or_none(v)` (`src/data/common.py`)

Core 모듈에서 널리 쓰이는 헬퍼. NaN/Inf 를 `None` 으로 변환해 안전하게 수치를 얻는다.

```python
def finite_or_none(v):
    """유한한 수치면 v 를, 아니면 None 을 반환한다."""
    if v is None:
        return None
    f = float(v)
    return None if (math.isnan(f) or math.isinf(f)) else f
```

### `_safe_get(info, key)` (`yahoo_client/_normalize.py`)

yfinance 의 info dict 에서 안전하게 값을 얻는다. NaN/Inf 는 `None` 으로 변환.

---

## 테스트 픽스처

| 파일 | 내용 | 용도 |
|:---|:---|:---|
| `tests/fixtures/stock_info.json` | stock_info 상당（27 필드, 삼성전자 005930.KS. 수치는 테스트용 가상값） | `conftest.py` 의 `stock_info_data` 픽스처 |
| `tests/fixtures/stock_detail.json` | stock_detail 상당（stock_info + 추가 필드） | `conftest.py` 의 `stock_detail_data` 픽스처 |
| `tests/fixtures/sample_portfolio.csv` | 포트폴리오 샘플（005930.KS, 000660.KS, 035420.KS, 105560.KS, 247540.KQ, 069500.KS, AAPL 7행） | KIK-745 worktree 용, 개인 PF 대체 |
| `tests/fixtures/sample_cash_balance.json` | 현금 잔고 샘플（total_krw 10,000,000） | KIK-745 worktree 용 |

테스트에서는 `monkeypatch` 로 `yahoo_client.get_stock_info` / `get_stock_detail` 을 모킹해 이 JSON 을 반환한다.
