#!/bin/bash
# ─────────────────────────────────────────────────────────
# Offsides Report — GitHub Setup Script
# Run this from inside the offsides-report/ folder
# ─────────────────────────────────────────────────────────

set -e

GITHUB_USER="morrdf3"
REPO_NAME="offsides-report"
API_KEY="61eb20663a32d31175fad82cf5ec8da9"

echo ""
echo "=== The Offsides Report — GitHub Setup ==="
echo ""

# Step 0: Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo "Installing GitHub CLI..."
    brew install gh 2>/dev/null || {
        echo ""
        echo "ERROR: Could not install gh CLI automatically."
        echo "Install it manually: https://cli.github.com"
        echo "Then re-run this script."
        exit 1
    }
fi

# Step 1: Authenticate if needed
if ! gh auth status &>/dev/null; then
    echo "You need to log in to GitHub first."
    echo ""
    gh auth login
fi

echo ""
echo "Step 1/5: Initializing git repo..."
git init
git add .
git commit -m "Initial commit: Offsides Report — golf EV analysis site"

echo ""
echo "Step 2/5: Creating GitHub repo..."
gh repo create "$REPO_NAME" --public --source=. --push

echo ""
echo "Step 3/5: Adding API key as a secret..."
echo "$API_KEY" | gh secret set ODDS_API_KEY

echo ""
echo "Step 4/5: Enabling GitHub Pages..."
gh api -X PUT "repos/$GITHUB_USER/$REPO_NAME/pages" \
    -f "source[branch]=main" \
    -f "source[path]=/docs" \
    2>/dev/null || \
gh api -X POST "repos/$GITHUB_USER/$REPO_NAME/pages" \
    -f "source[branch]=main" \
    -f "source[path]=/docs"

echo ""
echo "Step 5/5: Triggering first data update..."
gh workflow run update-odds.yml

echo ""
echo "==========================================="
echo "  DONE! Your site will be live at:"
echo ""
echo "  https://$GITHUB_USER.github.io/$REPO_NAME/"
echo ""
echo "  (Give it 2-3 minutes for Pages to deploy)"
echo "==========================================="
echo ""
echo "The site will auto-update at 8 AM and 5 PM Eastern daily."
echo "You can also trigger updates manually from the Actions tab."
