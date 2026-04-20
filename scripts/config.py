"""
Offsides Report - Configuration

API keys are loaded from environment variables for security.
Set ODDS_API_KEY in your environment or GitHub Secrets.
"""

import os

# ── The Odds API ──────────────────────────────────────────────
# Free tier: 500 requests/month
# Sign up at: https://the-odds-api.com
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# ── NC-Legal Sportsbooks ─────────────────────────────────────
NC_BOOKS = [
    "fanduel",
    "draftkings",
    "betmgm",
    "caesars",
    "espnbet",
    "bet365",
    "fanatics",
]

# ── Sharp Reference Books ────────────────────────────────────
SHARP_REFERENCE_BOOKS = [
    "pinnacle",
    "lowvig",
    "betonlineag",
]

# Human-readable names for display
BOOK_DISPLAY_NAMES = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "espnbet": "ESPN BET",
    "bet365": "Bet365",
    "fanatics": "Fanatics",
    "pinnacle": "Pinnacle",
    "betonlineag": "BetOnline",
    "bovada": "Bovada",
    "williamhill_us": "William Hill",
    "pointsbetus": "PointsBet",
    "unibet_us": "Unibet",
    "betrivers": "BetRivers",
    "superbook": "SuperBook",
    "wynnbet": "WynnBET",
    "betus": "BetUS",
    "lowvig": "LowVig",
    "mybookieag": "MyBookie",
}

# ── EV Thresholds (Time-Adjusted) ────────────────────────────
RISK_FREE_RATE = 0.045  # ~4.5% annualized
BASE_EDGE_MINIMUM = 0.02  # 2% minimum edge even for same-day bets

# ── Value Labels ─────────────────────────────────────────────
STRONG_VALUE_LABEL = "STRONG VALUE"
NOTABLE_VALUE_LABEL = "Notable Value"

# ── Golf Markets ─────────────────────────────────────────────
# All markets to request from The Odds API in a single call
# This maximizes data while minimizing API request usage
GOLF_MARKETS = "outrights,h2h"

# Display names for market types
MARKET_DISPLAY_NAMES = {
    "outrights": "Tournament Winner",
    "h2h": "Head-to-Head Matchups",
    "top_5": "Top 5 Finish",
    "top_10": "Top 10 Finish",
    "top_20": "Top 20 Finish",
}

# ── Newsletter Settings ───────────────────────────────────────
NEWSLETTER_NAME = "The Offsides Report"
NEWSLETTER_TAGLINE = "Finding where the books disagree"
NEWSLETTER_AUTHOR = "Dylan Morris"
