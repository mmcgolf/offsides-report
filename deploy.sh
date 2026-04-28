#!/bin/bash
# Offsides Report — One-command deploy
# Usage: ./deploy.sh
# Or:    ./deploy.sh "your commit message here"

set -e

cd "$(dirname "$0")"

MSG="${1:-Auto-deploy updates}"

# Pull remote changes FIRST (GitHub Actions updates data files remotely)
# Use --theirs to auto-resolve data file conflicts (they get regenerated)
git stash --include-untracked 2>/dev/null || true
git pull origin main --rebase || {
  echo "⚠ Resolving data file conflicts (they get regenerated anyway)..."
  git checkout --theirs docs/data/ 2>/dev/null || true
  git add docs/data/
  GIT_EDITOR=true git rebase --continue 2>/dev/null || git rebase --skip
}
git stash pop 2>/dev/null || true

# Stage code changes only (NOT data files — the workflow regenerates those)
git add scripts/ docs/index.html .github/ deploy.sh requirements.txt 2>/dev/null || true

# Check if there's anything to commit
if git diff --cached --quiet; then
  echo "✓ No code changes to deploy."
else
  git commit -m "$MSG"
  echo "✓ Committed: $MSG"
fi

git push origin main
echo "✓ Pushed to GitHub"

# Trigger data regeneration with the new code
gh workflow run update-odds.yml
echo "✓ Triggered odds update workflow"
echo ""
echo "Site will be live in ~30 seconds at:"
echo "  https://mmcgolf.github.io/offsides-report/"
