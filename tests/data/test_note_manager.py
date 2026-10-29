"""Tests for src.data.note_manager module (KIK-397, KIK-429).

Uses tmp_path for JSON file operations, Neo4j is mocked.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.note_manager import (
    save_note,
    load_notes,
    delete_note,
    _VALID_TYPES,
    _VALID_CATEGORIES,
)


# ===================================================================
# save_note tests
# ===================================================================

class TestSaveNote:
    def test_save_note_creates_file(self, tmp_path):
        note = save_note("005930.KS", "thesis", "Strong buy candidate", base_dir=str(tmp_path))

        assert note["symbol"] == "005930.KS"
        assert note["type"] == "thesis"
        assert note["content"] == "Strong buy candidate"
        assert note["id"].startswith("note_")
        assert "005930.KS" in note["id"]

        # Verify JSON file was created
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["content"] == "Strong buy candidate"

    def test_save_note_appends_same_date_symbol_type(self, tmp_path):
        save_note("005930.KS", "thesis", "First note", base_dir=str(tmp_path))
        save_note("005930.KS", "thesis", "Second note", base_dir=str(tmp_path))

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1  # Same file, appended
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["content"] == "First note"
        assert data[1]["content"] == "Second note"

    def test_save_note_different_types_separate_files(self, tmp_path):
        save_note("005930.KS", "thesis", "Thesis", base_dir=str(tmp_path))
        save_note("005930.KS", "concern", "Concern", base_dir=str(tmp_path))

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 2

    def test_save_note_invalid_type(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid note type"):
            save_note("005930.KS", "invalid_type", "content", base_dir=str(tmp_path))

    def test_save_note_valid_types(self):
        assert _VALID_TYPES == {"thesis", "observation", "concern", "review", "target", "lesson", "journal", "exit-rule"}

    def test_save_note_lesson_type(self, tmp_path):
        """lesson 타입 노트가 저장되는지 (KIK-408)."""
        note = save_note("005930.KS", "lesson", "Never chase momentum blindly", base_dir=str(tmp_path))
        assert note["type"] == "lesson"
        assert note["content"] == "Never chase momentum blindly"

    def test_save_note_source_field(self, tmp_path):
        note = save_note("005930.KS", "observation", "Note", source="health-check", base_dir=str(tmp_path))
        assert note["source"] == "health-check"

    def test_save_note_neo4j_failure_still_saves_json(self, tmp_path):
        """Neo4j failure should not prevent JSON write."""
        with patch("src.data.graph_store.merge_note", side_effect=Exception("Neo4j down")):
            note = save_note("005930.KS", "thesis", "content", base_dir=str(tmp_path))

        assert note["content"] == "content"
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_save_note_creates_directory(self, tmp_path):
        nested = tmp_path / "sub" / "notes"
        save_note("AAPL", "thesis", "test", base_dir=str(nested))
        assert nested.exists()

    def test_save_note_dot_in_symbol(self, tmp_path):
        """Dots in symbol should be replaced with underscore in filename."""
        save_note("247540.KQ", "thesis", "test", base_dir=str(tmp_path))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "247540_KQ" in files[0].name

    # KIK-429: category support
    def test_save_note_without_symbol(self, tmp_path):
        """symbol 없이 카테고리 지정으로 저장되는지."""
        note = save_note(note_type="review", content="PF analysis", category="portfolio", base_dir=str(tmp_path))
        assert note["symbol"] == ""
        assert note["category"] == "portfolio"
        assert "portfolio" in note["id"]
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "portfolio" in files[0].name

    def test_save_note_with_symbol_category_is_stock(self, tmp_path):
        """symbol 지정 시 category 가 자동으로 stock 이 되는지."""
        note = save_note("005930.KS", "thesis", "test", base_dir=str(tmp_path))
        assert note["category"] == "stock"

    def test_save_note_category_defaults_to_general(self, tmp_path):
        """symbol 도 category 도 미지정이면 general 이 되는지."""
        note = save_note(note_type="observation", content="test", base_dir=str(tmp_path))
        assert note["category"] == "general"

    def test_save_note_market_category(self, tmp_path):
        """market 카테고리로 저장되는지."""
        note = save_note(note_type="observation", content="Market memo", category="market", base_dir=str(tmp_path))
        assert note["category"] == "market"
        assert note["symbol"] == ""
        assert "market" in note["id"]

    def test_save_note_invalid_category(self, tmp_path):
        """무효한 카테고리는 에러가 되는지."""
        with pytest.raises(ValueError, match="Invalid category"):
            save_note(note_type="observation", content="test", category="invalid", base_dir=str(tmp_path))

    def test_valid_categories(self):
        assert _VALID_CATEGORIES == {"stock", "portfolio", "market", "general"}

    def test_save_note_symbol_with_invalid_category_ignored(self, tmp_path):
        """symbol 지정 시 무효 category 는 무시되고 stock 이 되는지."""
        note = save_note("005930.KS", "thesis", "test", category="invalid", base_dir=str(tmp_path))
        assert note["category"] == "stock"


# ===================================================================
# KIK-534: lesson trigger/expected_action tests
# ===================================================================

class TestSaveNoteLessonFields:
    def test_lesson_with_trigger_and_expected_action(self, tmp_path):
        """lesson 에 trigger 와 expected_action 이 저장되는지."""
        note = save_note(
            "005930.KS", "lesson", "고점에 물렸다",
            trigger="RSI 70 초과에서 매수",
            expected_action="RSI 70 초과에서는 사지 않는다",
            base_dir=str(tmp_path),
        )
        assert note["type"] == "lesson"
        assert note["trigger"] == "RSI 70 초과에서 매수"
        assert note["expected_action"] == "RSI 70 초과에서는 사지 않는다"

    def test_lesson_with_trigger_only(self, tmp_path):
        """trigger 만 지정."""
        note = save_note(
            "AAPL", "lesson", "Lost money",
            trigger="모멘텀에 뛰어들었다",
            base_dir=str(tmp_path),
        )
        assert note["trigger"] == "모멘텀에 뛰어들었다"
        assert "expected_action" not in note

    def test_lesson_with_expected_action_only(self, tmp_path):
        """expected_action 만 지정."""
        note = save_note(
            "AAPL", "lesson", "Learned patience",
            expected_action="거래량 확인 후 진입",
            base_dir=str(tmp_path),
        )
        assert "trigger" not in note
        assert note["expected_action"] == "거래량 확인 후 진입"

    def test_lesson_without_extra_fields(self, tmp_path):
        """trigger/expected_action 없는 lesson 은 기존과 동일."""
        note = save_note("005930.KS", "lesson", "Basic lesson", base_dir=str(tmp_path))
        assert note["type"] == "lesson"
        assert "trigger" not in note
        assert "expected_action" not in note

    def test_non_lesson_ignores_trigger(self, tmp_path):
        """lesson 이외 타입에서는 trigger/expected_action 이 무시되는지."""
        note = save_note(
            "005930.KS", "thesis", "test",
            trigger="should be ignored",
            expected_action="should be ignored",
            base_dir=str(tmp_path),
        )
        assert "trigger" not in note
        assert "expected_action" not in note

    def test_lesson_fields_persisted_in_json(self, tmp_path):
        """trigger/expected_action 이 JSON 파일에 영속화되는지."""
        save_note(
            "005930.KS", "lesson", "test",
            trigger="trigger_text",
            expected_action="action_text",
            base_dir=str(tmp_path),
        )
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["trigger"] == "trigger_text"
        assert notes[0]["expected_action"] == "action_text"


# ===================================================================
# KIK-473: journal note type tests
# ===================================================================

class TestSaveNoteJournal:
    def test_journal_type_in_valid_types(self):
        """journal 이 _VALID_TYPES 에 포함되는지."""
        assert "journal" in _VALID_TYPES

    def test_journal_without_symbol_or_category(self, tmp_path):
        """journal 타입은 symbol/category 없이 저장되는지."""
        note = save_note(note_type="journal", content="Today was quiet", base_dir=str(tmp_path))
        assert note["type"] == "journal"
        assert note["category"] == "general"
        assert note["symbol"] == ""

    def test_journal_auto_detects_symbols(self, tmp_path):
        """journal 의 content 에서 티커 심볼을 자동 검출하는지."""
        note = save_note(
            note_type="journal",
            content="NVDA가 급등. 005930.KS는 하락했다",
            base_dir=str(tmp_path),
        )
        detected = note.get("detected_symbols", [])
        assert set(detected) == {"NVDA", "005930.KS"}

    def test_journal_no_symbols_detected(self, tmp_path):
        """심볼 없는 journal 에는 detected_symbols 가 없는지."""
        note = save_note(
            note_type="journal",
            content="오늘은 거래하지 않는다",
            base_dir=str(tmp_path),
        )
        assert "detected_symbols" not in note

    def test_journal_with_explicit_symbol(self, tmp_path):
        """journal 도 symbol 지정 시 category 가 stock 이 되는지."""
        note = save_note(
            symbol="AAPL",
            note_type="journal",
            content="AAPL earnings coming up",
            base_dir=str(tmp_path),
        )
        assert note["category"] == "stock"
        assert note["symbol"] == "AAPL"
        # With explicit symbol, no auto-detection
        assert "detected_symbols" not in note

    def test_journal_with_category(self, tmp_path):
        """journal 도 category 지정을 존중하는지."""
        note = save_note(
            note_type="journal",
            content="Market reflections",
            category="market",
            base_dir=str(tmp_path),
        )
        assert note["category"] == "market"

    def test_journal_detected_symbols_max_3(self, tmp_path):
        """detected_symbols 는 최대 3건으로 제한되는지."""
        note = save_note(
            note_type="journal",
            content="NVDA AAPL MSFT GOOGL TSLA all up today",
            base_dir=str(tmp_path),
        )
        detected = note.get("detected_symbols", [])
        assert len(detected) <= 3


# ===================================================================
# load_notes tests
# ===================================================================

class TestLoadNotes:
    def _save_notes(self, tmp_path):
        """Save test notes and return them."""
        n1 = save_note("005930.KS", "thesis", "삼성전자 thesis", base_dir=str(tmp_path))
        n2 = save_note("AAPL", "concern", "Apple concern", base_dir=str(tmp_path))
        n3 = save_note("005930.KS", "concern", "삼성전자 concern", base_dir=str(tmp_path))
        return n1, n2, n3

    def test_load_all_notes(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 3

    def test_load_notes_filter_by_symbol(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(symbol="005930.KS", base_dir=str(tmp_path))
        assert len(notes) == 2
        assert all(n["symbol"] == "005930.KS" for n in notes)

    def test_load_notes_filter_by_type(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(note_type="concern", base_dir=str(tmp_path))
        assert len(notes) == 2
        assert all(n["type"] == "concern" for n in notes)

    def test_load_notes_filter_both(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(symbol="005930.KS", note_type="thesis", base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "삼성전자 thesis"

    def test_load_notes_empty_dir(self, tmp_path):
        notes = load_notes(base_dir=str(tmp_path))
        assert notes == []

    def test_load_notes_nonexistent_dir(self, tmp_path):
        notes = load_notes(base_dir=str(tmp_path / "nonexistent"))
        assert notes == []

    def test_load_notes_sorted_by_date_desc(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(base_dir=str(tmp_path))
        dates = [n["date"] for n in notes]
        assert dates == sorted(dates, reverse=True)

    def test_load_notes_corrupted_file(self, tmp_path):
        """Corrupted JSON files should be skipped."""
        (tmp_path / "bad.json").write_text("not valid json")
        save_note("005930.KS", "thesis", "Good note", base_dir=str(tmp_path))
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "Good note"

    # KIK-429: category filter
    def test_load_notes_filter_by_category(self, tmp_path):
        """category 필터로 좁힐 수 있는지."""
        save_note("005930.KS", "thesis", "Stock note", base_dir=str(tmp_path))
        save_note(note_type="review", content="PF note", category="portfolio", base_dir=str(tmp_path))
        save_note(note_type="observation", content="Market note", category="market", base_dir=str(tmp_path))

        stock_notes = load_notes(category="stock", base_dir=str(tmp_path))
        assert len(stock_notes) == 1
        assert stock_notes[0]["symbol"] == "005930.KS"

        pf_notes = load_notes(category="portfolio", base_dir=str(tmp_path))
        assert len(pf_notes) == 1
        assert pf_notes[0]["content"] == "PF note"

        market_notes = load_notes(category="market", base_dir=str(tmp_path))
        assert len(market_notes) == 1
        assert market_notes[0]["content"] == "Market note"

    def test_load_notes_all_includes_categorized(self, tmp_path):
        """전체 조회에 카테고리 있는 메모도 포함되는지."""
        save_note("AAPL", "thesis", "Stock", base_dir=str(tmp_path))
        save_note(note_type="review", content="PF", category="portfolio", base_dir=str(tmp_path))
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 2

    def test_load_notes_category_and_type_combined(self, tmp_path):
        """category + type 복합 필터가 올바르게 동작하는지."""
        save_note(note_type="review", content="PF review", category="portfolio", base_dir=str(tmp_path))
        save_note(note_type="observation", content="PF obs", category="portfolio", base_dir=str(tmp_path))
        save_note(note_type="review", content="Market review", category="market", base_dir=str(tmp_path))
        notes = load_notes(category="portfolio", note_type="review", base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "PF review"


# ===================================================================
# delete_note tests
# ===================================================================

class TestDeleteNote:
    def test_delete_note_found(self, tmp_path):
        note = save_note("005930.KS", "thesis", "To delete", base_dir=str(tmp_path))
        assert delete_note(note["id"], base_dir=str(tmp_path)) is True
        # File should be removed (was the only note)
        assert list(tmp_path.glob("*.json")) == []

    def test_delete_note_keeps_others(self, tmp_path):
        n1 = save_note("005930.KS", "thesis", "Keep me", base_dir=str(tmp_path))
        n2 = save_note("005930.KS", "thesis", "Delete me", base_dir=str(tmp_path))
        assert delete_note(n2["id"], base_dir=str(tmp_path)) is True
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "Keep me"

    def test_delete_note_not_found(self, tmp_path):
        save_note("005930.KS", "thesis", "Note", base_dir=str(tmp_path))
        assert delete_note("nonexistent_id", base_dir=str(tmp_path)) is False

    def test_delete_note_empty_dir(self, tmp_path):
        assert delete_note("any_id", base_dir=str(tmp_path)) is False

    def test_delete_note_nonexistent_dir(self, tmp_path):
        assert delete_note("any_id", base_dir=str(tmp_path / "nonexistent")) is False
