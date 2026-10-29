"""Notes Tool — 투자 메모·lesson 읽기/쓰기 파사드.

tools/ 층은 저장·조회만 담당한다. 판단 로직은 포함하지 않는다.
src/data/note_manager 의 순수 데이터 조작 함수를 re-export 한다.
JSON 파일이 master, Neo4j 는 view(dual-write).
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.note_manager import (  # noqa: E402
    save_note,
    load_notes,
    delete_note,
    get_exit_rules,
    check_exit_rule,
    check_lesson_conflicts,
)

__all__ = [
    "save_note",
    "load_notes",
    "delete_note",
    "get_exit_rules",
    "check_exit_rule",
    "check_lesson_conflicts",
]
