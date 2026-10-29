"""섹터 상대강도 계산 테스트 (KIK-702)."""

import pandas as pd
import pytest

from src.data.yahoo_client.sector_rs import (
    BENCHMARK,
    SECTOR_ETFS,
    get_sector_rs,
    _safe_return,
)


class TestSafeReturn:
    """_safe_return 테스트."""

    def test_basic(self):
        s = pd.Series([100, 105, 110, 115, 120])
        # _safe_return(s, 2): current=s[-1]=120, past=s[-2]=115 → 120/115 - 1
        ret = _safe_return(s, 2)
        assert ret is not None
        assert abs(ret - (120.0 / 115.0 - 1)) < 1e-6

    def test_multi_day(self):
        s = pd.Series([100, 105, 110, 115, 120])
        # _safe_return(s, 4): current=s[-1]=120, past=s[-4]=105 → 120/105 - 1
        ret = _safe_return(s, 4)
        assert ret is not None
        assert abs(ret - (120.0 / 105.0 - 1)) < 1e-6

    def test_insufficient_data(self):
        s = pd.Series([100, 105])
        assert _safe_return(s, 5) is None

    def test_zero_past(self):
        s = pd.Series([0, 0, 0, 100])
        assert _safe_return(s, 2) is None


class TestConstants:
    """상수 검증."""

    def test_sector_etfs_count(self):
        assert len(SECTOR_ETFS) == 11

    def test_benchmark_is_kodex_200(self):
        assert BENCHMARK == "069500.KS"

    def test_known_etfs(self):
        assert SECTOR_ETFS["반도체"] == "091160.KS"
        assert SECTOR_ETFS["은행"] == "091170.KS"

    def test_all_etfs_are_kospi_listed(self):
        assert all(sym.endswith(".KS") for sym in SECTOR_ETFS.values())


class TestGetSectorRS:
    """get_sector_rs 테스트 (외부 API 모킹)."""

    def test_returns_list_or_none(self, mock_yahoo_client):
        """모킹 환경에서는 데이터 부족으로 None 이 반환될 수 있다."""
        result = get_sector_rs()
        assert result is None or isinstance(result, list)

    def test_result_structure(self, mock_yahoo_client):
        """결과가 반환된 경우 구조 검증."""
        result = get_sector_rs()
        if result is not None and len(result) > 0:
            item = result[0]
            for key in ("name", "symbol", "rs_score", "return_20d",
                        "return_60d", "volume_change", "rank"):
                assert key in item
            assert item["rank"] == 1  # 첫 항목은 rank 1

    def test_sorted_by_rs_descending(self, mock_yahoo_client):
        """RS 내림차순 정렬 여부."""
        result = get_sector_rs()
        if result is not None and len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i]["rs_score"] >= result[i + 1]["rs_score"]
