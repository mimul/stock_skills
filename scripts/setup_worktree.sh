#!/usr/bin/env bash
# scripts/setup_worktree.sh — KIK-745
#
# 개발용 worktree 를 만들고 tests/fixtures/ 의 샘플 데이터를 data/ 에
# 복사해 즉시 개발·통합 시험이 가능한 상태로 만든다.
#
# Usage:
#   bash scripts/setup_worktree.sh KIK-NNN [short-desc]
#
# Example:
#   bash scripts/setup_worktree.sh KIK-748 add-feature
#
# 중요:
#   개인 PF 데이터(~/stock-skills/data/portfolio.csv 등)는 **절대로**
#   복사하지 않는다. 범용 테스트 종목만 포함한 sample fixture 를 사용한다.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 KIK-NNN [short-desc]" >&2
    exit 1
fi

ISSUE="$1"
SHORT_DESC="${2:-task}"

# Issue 번호를 소문자화（KIK-748 → kik748）
ISSUE_LOWER=$(echo "$ISSUE" | tr '[:upper:]' '[:lower:]' | tr -d '-')
BRANCH="feature/$(echo "$ISSUE" | tr '[:upper:]' '[:lower:]')-${SHORT_DESC}"
WORKTREE="${HOME}/stock-skills-${ISSUE_LOWER}"

# main repo 경로（이 스크립트가 놓인 리포지토리의 루트）
MAIN_REPO="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -d "$WORKTREE" ]]; then
    echo "Error: worktree already exists at $WORKTREE" >&2
    exit 1
fi

echo "Creating worktree:"
echo "  branch:  $BRANCH"
echo "  path:    $WORKTREE"
git -C "$MAIN_REPO" worktree add -b "$BRANCH" "$WORKTREE" main

echo "Seeding sample fixtures (NOT personal PF):"
mkdir -p "$WORKTREE/data"
cp "$MAIN_REPO/tests/fixtures/sample_portfolio.csv" "$WORKTREE/data/portfolio.csv"
cp "$MAIN_REPO/tests/fixtures/sample_cash_balance.json" "$WORKTREE/data/cash_balance.json"
echo "  ✓ data/portfolio.csv      (from sample_portfolio.csv)"
echo "  ✓ data/cash_balance.json  (from sample_cash_balance.json)"

cat <<EOF2

✅ Worktree ready: $WORKTREE
   cd $WORKTREE
   python3 -m pytest tests/ -q   # ← 개인 데이터 없이 유닛 테스트 통과

⚠ 주의:
   이 worktree 에는 범용 테스트 종목만 들어 있습니다.
   개인 PF 를 반영한 통합 시험이 필요하면 환경 변수로 참조하세요:
     export STOCK_SKILLS_DATA_DIR=$HOME/stock-skills/data
   개인 PF 를 worktree 에 cp 하지 마세요（실수로 커밋되는 것을 방지）.
EOF2
