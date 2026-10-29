"""Shared pytest fixtures for stock-skills test suite."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# Add project root to sys.path so that `from src.xxx import yyy` works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixture data loaders
# ---------------------------------------------------------------------------

@pytest.fixture
def stock_info_data() -> dict:
    """stock_info.json 픽스처 로드 (삼성전자 005930.KS 기본 정보).

    수치는 실제 삼성전자 데이터가 아닌 테스트용 가상값.
    """
    path = FIXTURES_DIR / "stock_info.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def stock_detail_data() -> dict:
    """stock_detail.json 픽스처 로드 (삼성전자 005930.KS 상세 정보).

    수치는 실제 삼성전자 데이터가 아닌 테스트용 가상값.
    """
    path = FIXTURES_DIR / "stock_detail.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def etf_info_data() -> dict:
    """Load the etf_info.json fixture (VGK basic info)."""
    path = FIXTURES_DIR / "etf_info.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def etf_detail_data() -> dict:
    """Load the etf_detail.json fixture (VGK detailed info)."""
    path = FIXTURES_DIR / "etf_detail.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def price_history_df() -> pd.DataFrame:
    """Load the price_history.csv fixture as a pandas DataFrame.

    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    250 rows representing an uptrend with a pullback pattern.
    """
    path = FIXTURES_DIR / "price_history.csv"
    df = pd.read_csv(path)
    return df


# ---------------------------------------------------------------------------
# Yahoo client mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_yahoo_client(monkeypatch):
    """Mock yahoo_client API calls to avoid real network requests.

    Usage in tests:
        def test_something(mock_yahoo_client, stock_info_data):
            mock_yahoo_client.get_stock_info.return_value = stock_info_data
            # ... call code that uses yahoo_client ...
    """
    from src.data import yahoo_client

    mock = MagicMock()

    # Default return values (can be overridden per-test)
    mock.get_stock_info.return_value = None
    mock.get_stock_detail.return_value = None
    mock.get_multiple_stocks.return_value = {}
    mock.screen_stocks.return_value = []
    mock.get_price_history.return_value = None

    # Patch each function on the yahoo_client module
    monkeypatch.setattr(yahoo_client, "get_stock_info", mock.get_stock_info)
    monkeypatch.setattr(yahoo_client, "get_stock_detail", mock.get_stock_detail)
    monkeypatch.setattr(yahoo_client, "get_multiple_stocks", mock.get_multiple_stocks)
    monkeypatch.setattr(yahoo_client, "screen_stocks", mock.screen_stocks)
    monkeypatch.setattr(yahoo_client, "get_price_history", mock.get_price_history)

    return mock


# ---------------------------------------------------------------------------
# Auto-mock external services (KIK-529)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _block_external_io(request, monkeypatch):
    """Block Neo4j / TEI / Grok I/O in all tests.

    Tests that directly test these clients should add:
        pytestmark = pytest.mark.no_auto_mock
    """
    if request.node.get_closest_marker("no_auto_mock"):
        return

    # Neo4j: _get_mode() returns "off" → all merge_* return False immediately
    monkeypatch.setenv("NEO4J_MODE", "off")
    monkeypatch.setattr("src.data.graph_store._get_driver", lambda: None)
    monkeypatch.setattr("src.data.graph_store.is_available", lambda: False)
    # TODO(next-issue): drop this monkeypatch — `_unavailable_warned` is now
    # only consulted inside is_available(), which is already stubbed above.
    monkeypatch.setattr("src.data.graph_store._unavailable_warned", True)
    # KIK-743: mode cache 의 TTL 30s 때문에 테스트 간 값이 누출되므로,
    #          fixture 시작 시 명시적으로 리셋해 monkeypatch 를 확실히 반영한다.
    try:
        from src.data.graph_store._common import reset_mode_cache
        reset_mode_cache()
    except ImportError:
        pass

    # KRX(pykrx): 개발자 셸의 자격 증명이 테스트로 새지 않도록 제거 + 세션 상태 초기화
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    from src.data.kr_valuation import _pykrx_provider as _pk
    _pk.reset_state()

    # TEI: no HTTP calls
    from src.data import embedding_client as _ec
    monkeypatch.setattr(_ec, "is_available", lambda: False)
    monkeypatch.setattr(_ec, "get_embedding", lambda text: None)

    # Grok: ensure no API key → functions return EMPTY_* immediately
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    # In-memory cache: clear between tests to prevent cross-test leaks (KIK-531)
    from src.data.yahoo_client._memory_cache import clear_memory_cache
    clear_memory_cache()
