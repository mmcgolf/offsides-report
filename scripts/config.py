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

# ── Sport Groups ─────────────────────────────────────────────
# Each group defines which API sport keys belong to it.
# The /sports endpoint returns all active keys; we match them
# to groups by prefix pattern. This is dynamic — when the API
# adds "americanfootball_nfl_afc_winner" it auto-sorts into NFL.

SPORT_GROUPS = {
    "golf": {
        "display_name": "Golf",
        "icon": "⛳",
        "key_patterns": ["golf"],
        "markets": "outrights,h2h",
        "typical_resolution_days": 4,
    },
    "nba": {
        "display_name": "NBA",
        "icon": "🏀",
        "key_patterns": ["basketball_nba"],
        "markets": "outrights,h2h",
        "typical_resolution_days": 120,
    },
    "ncaab": {
        "display_name": "NCAAB",
        "icon": "🏀",
        "key_patterns": ["basketball_ncaab"],
        "markets": "outrights,h2h",
        "typical_resolution_days": 90,
    },
    "nfl": {
        "display_name": "NFL",
        "icon": "🏈",
        "key_patterns": ["americanfootball_nfl"],
        "markets": "outrights,h2h",
        "typical_resolution_days": 180,
    },
    "ncaaf": {
        "display_name": "NCAAF",
        "icon": "🏈",
        "key_patterns": ["americanfootball_ncaaf"],
        "markets": "outrights,h2h",
        "typical_resolution_days": 150,
    },
}

# ── Display Names ────────────────────────────────────────────
# Market type display names
MARKET_DISPLAY_NAMES = {
    "outrights": "Futures / Winner",
    "h2h": "Head-to-Head / Moneyline",
    "spreads": "Spreads",
    "totals": "Totals (O/U)",
}

# Clean up sport key names for display
# Maps API key fragments to readable names
SPORT_KEY_DISPLAY = {
    # Golf
    "golf_masters_tournament_winner": "Masters",
    "golf_pga_championship_winner": "PGA Championship",
    "golf_us_open_winner": "US Open",
    "golf_the_open_championship_winner": "The Open Championship",
    "golf_pga_tour": "PGA Tour (This Week)",
    # NBA
    "basketball_nba_championship_winner": "NBA Championship",
    "basketball_nba_championship": "NBA Championship",
    "basketball_nba_eastern_conference_winner": "Eastern Conference",
    "basketball_nba_western_conference_winner": "Western Conference",
    "basketball_nba_mvp": "NBA MVP",
    "basketball_nba": "NBA (Game Lines)",
    # NCAAB
    "basketball_ncaab_championship_winner": "NCAAB Championship",
    "basketball_ncaab_championship": "NCAAB Championship",
    "basketball_ncaab": "NCAAB (Game Lines)",
    # NFL
    "americanfootball_nfl_super_bowl_winner": "Super Bowl Winner",
    "americanfootball_nfl_super_bowl": "Super Bowl Winner",
    "americanfootball_nfl_afc_championship_winner": "AFC Champion",
    "americanfootball_nfl_nfc_championship_winner": "NFC Champion",
    "americanfootball_nfl_afc_conference_winner": "AFC Champion",
    "americanfootball_nfl_nfc_conference_winner": "NFC Champion",
    "americanfootball_nfl_mvp": "NFL MVP",
    "americanfootball_nfl": "NFL (Game Lines)",
    # NCAAF
    "americanfootball_ncaaf_championship_winner": "CFP National Championship",
    "americanfootball_ncaaf_championship": "CFP National Championship",
    "americanfootball_ncaaf": "NCAAF (Game Lines)",
}

# ── Newsletter Settings ───────────────────────────────────────
NEWSLETTER_NAME = "The Offsides Report"
NEWSLETTER_TAGLINE = "Finding where the books disagree"
NEWSLETTER_AUTHOR = "Dylan Morris"
