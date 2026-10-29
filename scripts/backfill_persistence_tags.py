"""Backfill `persistence` tag for existing lesson notes (KIK-739 Phase 1).

Each lesson is classified by Gemini into one of:
  - permanent:   영속적인 규칙 (매매 단위, PF 균형 normal, conviction 등)
  - situational: 문맥 의존 사례 (NFLX 반성, CEG 섹터 고정관념 등)
  - seasonal:    시계열·시황 의존 (유가 급등, 금리 4% 초과 등)
  - expired:     이미 진부화된 것

Usage
-----
Dry-run (CSV report only):
    python3 scripts/backfill_persistence_tags.py --dry-run

Apply:
    python3 scripts/backfill_persistence_tags.py --execute

Limit (debug):
    python3 scripts/backfill_persistence_tags.py --dry-run --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from tools.llm import call_llm  # noqa: E402
from tools.notes import load_notes  # noqa: E402
from src.data.note_manager import update_lesson_metadata, _VALID_PERSISTENCE  # noqa: E402


_SYSTEM_PROMPT = """\
당신은 투자 lesson 의 영속성(persistence) 분류기입니다. lesson 의 content 와 trigger / \
expected_action 을 보고 그 교훈이 시간이 지나며 어떻게 변하는지를 4단계로 분류합니다.

분류 규칙:
- permanent: 보편적인 투자 원칙·거래 제약. 시간이 지나도 무효화되지 않는다.
  예: 주식의 최소 매매 단위, conviction 을 존중하는 원칙, 수량 계산 확인, PF 균형 설계 규칙,
      lesson 의 표면적 해석 금지, 추천 편향에 대한 주의, 통화 배분 시뮬레이션 원칙
- situational: 특정 종목·특정 섹터·특정 상황의 사례에서 얻은 교훈. 문맥이 맞을 때만 유효.
  예: NFLX 역추세 conviction 사례, CEG 의 섹터 고정관념 편향, 특정 종목의 익절 타이밍
- seasonal: 매크로 환경·시황·지정학·금리 수준 등 시간이 지나면 무효가 될 수 있는 교훈.
  예: 유가 급등 시 헤지, 금리 4% 초과 + VIX 25 초과 상황, 특정 시점의 통화정책 스탠스
- expired: 이미 진부화되어 참조하면 안 되는 것. 옛 시황에 의존해 전제가 무너진 것.

신중 판정 원칙:
- 망설여지면 situational (문맥 의존) 을 고른다. permanent 는 명확히 "언제나 유효" 한 것에 한정
- expired 는 정말 "이미 무효" 라고 확신할 때만. 보통은 seasonal 로 남긴다

출력은 아래 JSON 만. 설명문 금지.
{"persistence": "permanent" | "situational" | "seasonal" | "expired", "reason": "한 줄 판정 이유"}
"""

_USER_TEMPLATE = """\
다음 lesson 의 영속성을 분류하라.

date: {date}
symbol: {symbol}
trigger: {trigger}
expected_action: {expected_action}
content (요약):
\"\"\"
{content}
\"\"\"
"""


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    payload = fence.group(1) if fence else text
    brace = re.search(r"\{.*\}", payload, re.S)
    if not brace:
        return None
    try:
        obj = json.loads(brace.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _classify(lesson: dict) -> dict | None:
    """Call Gemini to classify the persistence of a lesson."""
    prompt = _USER_TEMPLATE.format(
        date=lesson.get("date", "(unknown)"),
        symbol=lesson.get("symbol") or "(none)",
        trigger=(lesson.get("trigger") or "(none)")[:200],
        expected_action=(lesson.get("expected_action") or "(none)")[:200],
        content=(lesson.get("content") or "")[:1500],
    )
    raw = call_llm(
        provider="gemini",
        model="gemini-2.5-pro",
        prompt=prompt,
        system_prompt=_SYSTEM_PROMPT,
        timeout=60,
    )
    if not raw:
        return None
    obj = _extract_json(raw)
    if not obj:
        return None
    persistence = (obj.get("persistence") or "").strip().lower()
    if persistence not in _VALID_PERSISTENCE:
        return None
    return {"persistence": persistence, "reason": (obj.get("reason") or "").strip()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backfill lesson persistence tags (KIK-739)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--execute", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--csv-out", default="/tmp/persistence_backfill.csv",
        help="CSV report path (dry-run mode)",
    )
    p.add_argument(
        "--reclassify-all", action="store_true",
        help="Re-classify even lessons that already have a persistence tag",
    )
    args = p.parse_args(argv)

    lessons = load_notes(note_type="lesson")
    if args.reclassify_all:
        targets = lessons
    else:
        targets = [l for l in lessons if not l.get("persistence")]
    if args.limit:
        targets = targets[: args.limit]

    print(f"Total lessons: {len(lessons)}, target: {len(targets)}", file=sys.stderr)
    if not targets:
        print("Nothing to backfill.", file=sys.stderr)
        return 0

    rows: list[dict] = []
    applied = 0
    for i, lesson in enumerate(targets, 1):
        nid = lesson.get("id", "")
        date = lesson.get("date", "")
        print(f"[{i}/{len(targets)}] {date} {nid[:30]} ...", file=sys.stderr, end=" ", flush=True)
        cls = _classify(lesson)
        if cls is None:
            print("SKIP (classify failed)", file=sys.stderr)
            rows.append({
                "id": nid, "date": date, "persistence": "(failed)", "reason": "",
                "trigger": lesson.get("trigger", "")[:60],
            })
            continue
        rows.append({
            "id": nid, "date": date,
            "persistence": cls["persistence"], "reason": cls["reason"],
            "trigger": lesson.get("trigger", "")[:60],
        })
        if args.execute:
            updated = update_lesson_metadata(nid, persistence=cls["persistence"])
            if updated is None:
                print(f"WARN (update failed) - {cls['persistence']}", file=sys.stderr)
            else:
                applied += 1
                print(f"OK {cls['persistence']:<12} {cls['reason'][:40]}", file=sys.stderr)
        else:
            print(f"OK (dry) {cls['persistence']:<12} {cls['reason'][:40]}", file=sys.stderr)

    out_path = Path(args.csv_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "date", "persistence", "reason", "trigger"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV report: {out_path}", file=sys.stderr)

    # Distribution summary
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["persistence"]] = counts.get(r["persistence"], 0) + 1
    print(f"Distribution: {counts}", file=sys.stderr)

    if args.execute:
        print(f"Applied: {applied}/{len(targets)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
