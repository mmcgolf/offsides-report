"""
Offsides Report - Multi-Sport Odds Data Fetcher

Fetches odds from The Odds API for ALL active events across
Golf, NBA, NCAAB, NFL, and NCAAF.
Optimized for free tier (500 requests/month).
"""

import json
import os
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import (
    ODDS_API_KEY, ODDS_API_BASE, BOOK_DISPLAY_NAMES,
    SPORT_GROUPS, SPORT_KEY_DISPLAY,
)


def fetch_all_active_sports(api_key: str) -> list[dict]:
    """
    Discover ALL active sport keys from The Odds API.
    Costs 1 API request. Returns the full list; caller filters by group.
    """
    url = f"{ODDS_API_BASE}/sports"
    params = {"apiKey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  API requests remaining: {remaining}")
        all_sports = resp.json()
        active = [s for s in all_sports if s.get("active", False)]
        return active
    except Exception as e:
        print(f"  API error fetching sports: {e}")
        return []


def classify_sport(sport_key: str) -> Optional[str]:
    """
    Classify an API sport key into one of our sport groups.
    Returns the group key (e.g., 'golf', 'nba') or None if unrecognized.
    """
    key_lower = sport_key.lower()
    for group_key, group_cfg in SPORT_GROUPS.items():
        for pattern in group_cfg["key_patterns"]:
            if key_lower.startswith(pattern):
                return group_key
    return None


def get_event_display_name(sport_key: str, api_title: str) -> str:
    """Get a clean display name for an event/sport key."""
    if sport_key in SPORT_KEY_DISPLAY:
        return SPORT_KEY_DISPLAY[sport_key]
    # Fallback: use the API title
    return api_title


def fetch_all_odds(api_key: str) -> dict[str, list[dict]]:
    """
    Fetch odds for ALL active events across all configured sports.

    Strategy to minimize API usage:
    1. One call to /sports to discover everything active (1 request)
    2. One call per active sport key with all markets (N requests)

    Returns: {sport_group: [event_dicts]}
    """
    if not api_key:
        print("  No API key — using demo data")
        return get_demo_all_sports()

    # Step 1: Discover active sports
    print("\n  Discovering active sports...")
    active_sports = fetch_all_active_sports(api_key)

    if not active_sports:
        print("  No active sports found — using demo data")
        return get_demo_all_sports()

    # Step 2: Filter and classify into our groups
    grouped = {}
    for sport in active_sports:
        sport_key = sport["key"]
        group = classify_sport(sport_key)
        if group:
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(sport)

    for group_key, sports in grouped.items():
        display = SPORT_GROUPS[group_key]["display_name"]
        print(f"  {display}: {len(sports)} active market(s)")
        for s in sports:
            print(f"    - {s['key']}: {s.get('title', 'Unknown')}")

    if not grouped:
        print("  No matching sports found — using demo data")
        return get_demo_all_sports()

    # Step 3: Fetch odds for each active sport key
    results = {}
    for group_key, sports in grouped.items():
        group_cfg = SPORT_GROUPS[group_key]
        markets = group_cfg["markets"]
        results[group_key] = []

        for sport in sports:
            sport_key = sport["key"]
            sport_title = sport.get("title", sport_key)
            display_name = get_event_display_name(sport_key, sport_title)

            url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
            params = {
                "apiKey": api_key,
                "regions": "us",
                "markets": markets,
                "oddsFormat": "american",
            }

            try:
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                remaining = resp.headers.get("x-requests-remaining", "?")
                print(f"  {sport_key}: fetched odds (remaining: {remaining})")

                data = resp.json()
                if isinstance(data, list):
                    for event in data:
                        event["_sport_key"] = sport_key
                        event["_sport_title"] = display_name
                        event["_sport_group"] = group_key
                        results[group_key].append(event)
                elif isinstance(data, dict) and "bookmakers" in data:
                    data["_sport_key"] = sport_key
                    data["_sport_title"] = display_name
                    data["_sport_group"] = group_key
                    results[group_key].append(data)
            except Exception as e:
                print(f"  {sport_key}: error — {e}")

    return results


def parse_event_odds(event: dict) -> dict:
    """
    Parse a single event's odds into our internal format.
    Works for all sports — golf, NBA, NFL, NCAAB, NCAAF.
    Handles outrights, h2h (moneyline), spreads, totals.
    """
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    result = {
        "event_id": event.get("id", "unknown"),
        "event_name": event.get("_sport_title", event.get("sport_title", "Event")),
        "sport_key": event.get("_sport_key", event.get("sport_key", "unknown")),
        "sport_group": event.get("_sport_group", ""),
        "event_date": event.get("commence_time", ""),
        "home_team": event.get("home_team", ""),
        "away_team": event.get("away_team", ""),
        "markets": {},
    }

    bookmakers = event.get("bookmakers", [])

    for bm in bookmakers:
        book_key = bm.get("key", "unknown")

        for market in bm.get("markets", []):
            market_key = market.get("key", "unknown")

            if market_key in ("outrights", "top_5", "top_10", "top_20"):
                _parse_outright_market(result, market, market_key, book_key)
            elif market_key == "h2h":
                # For team sports, h2h is moneyline (2-way outright)
                # For golf, h2h is player matchups
                sport_group = result.get("sport_group", "")
                if sport_group == "golf":
                    _parse_h2h_golf(result, market, book_key)
                else:
                    _parse_h2h_team_sport(result, market, book_key, event)

    return result


def _parse_outright_market(result: dict, market: dict, market_key: str, book_key: str):
    """Parse an outright-style market (winner, top 5, top 10, etc.)."""
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    if market_key not in result["markets"]:
        result["markets"][market_key] = {
            "outcomes_by_book": {},
            "odds_by_book": {},
            "decimal_odds_by_book": {},
        }

    mkt = result["markets"][market_key]
    implied_probs = {}
    american_odds = {}
    decimal_odds = {}

    for outcome in market.get("outcomes", []):
        name = outcome.get("name", "Unknown")
        price = outcome.get("price", 0)

        if price != 0:
            dec = american_to_decimal(price)
            implied_probs[name] = decimal_to_implied_prob(dec)
            american_odds[name] = price
            decimal_odds[name] = dec

    if implied_probs:
        mkt["outcomes_by_book"][book_key] = implied_probs
        mkt["odds_by_book"][book_key] = american_odds
        mkt["decimal_odds_by_book"][book_key] = decimal_odds


def _parse_h2h_golf(result: dict, market: dict, book_key: str):
    """Parse golf head-to-head matchup market into structured matchup pairs."""
    if "h2h" not in result["markets"]:
        result["markets"]["h2h"] = {"matchups_by_book": {}}

    outcomes = market.get("outcomes", [])
    if len(outcomes) < 2:
        return

    matchup_pairs = []
    for i in range(0, len(outcomes) - 1, 2):
        a = outcomes[i]
        b = outcomes[i + 1]
        matchup_pairs.append({
            "player_a": a.get("name", "Unknown"),
            "price_a": a.get("price", 0),
            "player_b": b.get("name", "Unknown"),
            "price_b": b.get("price", 0),
        })

    result["markets"]["h2h"]["matchups_by_book"][book_key] = matchup_pairs


def _parse_h2h_team_sport(result: dict, market: dict, book_key: str, event: dict):
    """
    Parse team sport h2h (moneyline) as an outright-style market.
    For NBA/NFL game lines, h2h is just home vs away moneyline —
    treat it like a 2-outcome outright so EV engine works the same.
    """
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    if "h2h" not in result["markets"]:
        result["markets"]["h2h"] = {
            "outcomes_by_book": {},
            "odds_by_book": {},
            "decimal_odds_by_book": {},
        }

    mkt = result["markets"]["h2h"]
    implied_probs = {}
    american_odds = {}
    decimal_odds = {}

    for outcome in market.get("outcomes", []):
        name = outcome.get("name", "Unknown")
        price = outcome.get("price", 0)

        if price != 0:
            dec = american_to_decimal(price)
            implied_probs[name] = decimal_to_implied_prob(dec)
            american_odds[name] = price
            decimal_odds[name] = dec

    if implied_probs:
        mkt["outcomes_by_book"][book_key] = implied_probs
        mkt["odds_by_book"][book_key] = american_odds
        mkt["decimal_odds_by_book"][book_key] = decimal_odds


# ── Demo Data ─────────────────────────────────────────────────

def get_demo_all_sports() -> dict[str, list[dict]]:
    """Return demo data for all sports."""
    return {
        "golf": _get_demo_golf_events(),
        "nba": _get_demo_nba_events(),
        "nfl": _get_demo_nfl_events(),
        "ncaab": _get_demo_ncaab_events(),
        "ncaaf": _get_demo_ncaaf_events(),
    }


def _get_demo_golf_events() -> list[dict]:
    today = datetime.now()
    thursday = today + timedelta(days=(3 - today.weekday()) % 7)
    return [
        {
            "id": "demo_zurich_classic_2026",
            "_sport_key": "golf_pga_tour",
            "_sport_title": "Zurich Classic of New Orleans",
            "_sport_group": "golf",
            "commence_time": thursday.strftime("%Y-%m-%dT13:00:00Z"),
            "bookmakers": _demo_golf_bookmakers({"Scottie Scheffler": 650, "Collin Morikawa": 1400, "Xander Schauffele": 1100, "Rory McIlroy": 1200, "Patrick Cantlay": 1800, "Matt Fitzpatrick": 2200, "Shane Lowry": 2500, "Justin Thomas": 2000, "Tommy Fleetwood": 2800, "Hideki Matsuyama": 1600, "Viktor Hovland": 2000, "Sahith Theegala": 2500, "Wyndham Clark": 2200, "Tom Kim": 3000, "Cameron Young": 3500, "Corey Conners": 3000, "Sungjae Im": 3500, "Akshay Bhatia": 4000, "Brian Harman": 4500, "Russell Henley": 4000}),
        },
        {
            "id": "demo_pga_champ_2026",
            "_sport_key": "golf_pga_championship_winner",
            "_sport_title": "PGA Championship",
            "_sport_group": "golf",
            "commence_time": "2026-05-14T13:00:00Z",
            "bookmakers": _demo_golf_bookmakers({"Scottie Scheffler": 500, "Xander Schauffele": 800, "Rory McIlroy": 900, "Collin Morikawa": 1100, "Hideki Matsuyama": 1600, "Patrick Cantlay": 1800, "Viktor Hovland": 2000, "Sahith Theegala": 2200, "Matt Fitzpatrick": 2500, "Justin Thomas": 2200, "Tommy Fleetwood": 2800, "Shane Lowry": 2800, "Wyndham Clark": 2500, "Tom Kim": 3000, "Cameron Young": 3500, "Corey Conners": 3500, "Sungjae Im": 4000, "Akshay Bhatia": 3500, "Brian Harman": 5000, "Russell Henley": 4500}),
        },
        {
            "id": "demo_us_open_2026",
            "_sport_key": "golf_us_open_winner",
            "_sport_title": "US Open",
            "_sport_group": "golf",
            "commence_time": "2026-06-18T13:00:00Z",
            "bookmakers": _demo_golf_bookmakers({"Scottie Scheffler": 450, "Xander Schauffele": 850, "Rory McIlroy": 1000, "Collin Morikawa": 1200, "Hideki Matsuyama": 1800, "Patrick Cantlay": 2000, "Matt Fitzpatrick": 2000, "Wyndham Clark": 2000, "Viktor Hovland": 2200, "Sahith Theegala": 2500, "Justin Thomas": 2500, "Tommy Fleetwood": 3000, "Shane Lowry": 3000, "Tom Kim": 3500, "Cameron Young": 4000, "Corey Conners": 4000, "Sungjae Im": 4500, "Akshay Bhatia": 4000, "Brian Harman": 5000, "Russell Henley": 5000}),
        },
    ]


def _demo_golf_bookmakers(players_base: dict) -> list:
    """Generate bookmakers with disagreement for golf."""
    book_offsets = {
        "fanduel": {},
        "draftkings": {k: (-200 if i % 5 == 1 else 200 if i % 7 == 0 else 0) for i, k in enumerate(players_base)},
        "betmgm": {k: (500 if i % 4 == 0 else 0) for i, k in enumerate(players_base)},
        "caesars": {k: (300 if i % 6 == 2 else 0) for i, k in enumerate(players_base)},
        "espnbet": {k: (400 if i % 5 == 3 else 0) for i, k in enumerate(players_base)},
        "pinnacle": {k: (-30 if i < 3 else 0) for i, k in enumerate(players_base)},
        "lowvig": {k: (-20 if i < 2 else 0) for i, k in enumerate(players_base)},
    }
    bookmakers = []
    for book_key, offsets in book_offsets.items():
        outcomes = [{"name": p, "price": max(players_base[p] + offsets.get(p, 0), 100)} for p in players_base]
        bookmakers.append({"key": book_key, "title": BOOK_DISPLAY_NAMES.get(book_key, book_key), "markets": [{"key": "outrights", "outcomes": outcomes}]})
    return bookmakers


def _get_demo_nba_events() -> list[dict]:
    return [
        _demo_futures_event(
            "demo_nba_champ", "basketball_nba_championship_winner", "NBA Championship", "nba",
            "2026-06-15T00:00:00Z",
            {"Boston Celtics": 250, "Oklahoma City Thunder": 350, "Cleveland Cavaliers": 600,
             "New York Knicks": 800, "Denver Nuggets": 1200, "Minnesota Timberwolves": 1400,
             "Dallas Mavericks": 1600, "Milwaukee Bucks": 1800, "Phoenix Suns": 2000,
             "Golden State Warriors": 2500, "LA Clippers": 3000, "Philadelphia 76ers": 3500,
             "Miami Heat": 4000, "Los Angeles Lakers": 4500, "Sacramento Kings": 5000,
             "Indiana Pacers": 5500, "Memphis Grizzlies": 6000, "Houston Rockets": 6500,
             "New Orleans Pelicans": 8000, "Atlanta Hawks": 10000}),
        _demo_futures_event(
            "demo_nba_east", "basketball_nba_eastern_conference_winner", "Eastern Conference", "nba",
            "2026-06-01T00:00:00Z",
            {"Boston Celtics": 130, "Cleveland Cavaliers": 300, "New York Knicks": 400,
             "Milwaukee Bucks": 800, "Philadelphia 76ers": 1200, "Miami Heat": 1500,
             "Indiana Pacers": 2000, "Orlando Magic": 2500, "Atlanta Hawks": 4000,
             "Chicago Bulls": 8000}),
        _demo_futures_event(
            "demo_nba_west", "basketball_nba_western_conference_winner", "Western Conference", "nba",
            "2026-06-01T00:00:00Z",
            {"Oklahoma City Thunder": 180, "Denver Nuggets": 500, "Minnesota Timberwolves": 600,
             "Dallas Mavericks": 700, "Phoenix Suns": 900, "Golden State Warriors": 1200,
             "LA Clippers": 1600, "Los Angeles Lakers": 2000, "Sacramento Kings": 2500,
             "Houston Rockets": 3000, "Memphis Grizzlies": 3500, "New Orleans Pelicans": 5000}),
    ]


def _get_demo_nfl_events() -> list[dict]:
    return [
        _demo_futures_event(
            "demo_nfl_sb", "americanfootball_nfl_super_bowl_winner", "Super Bowl Winner", "nfl",
            "2027-02-14T00:00:00Z",
            {"Kansas City Chiefs": 500, "Detroit Lions": 600, "Buffalo Bills": 700,
             "Philadelphia Eagles": 800, "Baltimore Ravens": 1000, "San Francisco 49ers": 1200,
             "Green Bay Packers": 1400, "Houston Texans": 1600, "Dallas Cowboys": 1800,
             "Cincinnati Bengals": 2000, "Miami Dolphins": 2200, "Pittsburgh Steelers": 2500,
             "Minnesota Vikings": 2800, "Los Angeles Rams": 3000, "Jacksonville Jaguars": 3500,
             "Cleveland Browns": 4000, "New York Jets": 4500, "Denver Broncos": 5000,
             "Atlanta Falcons": 5500, "Seattle Seahawks": 6000}),
        _demo_futures_event(
            "demo_nfl_afc", "americanfootball_nfl_afc_conference_winner", "AFC Champion", "nfl",
            "2027-01-25T00:00:00Z",
            {"Kansas City Chiefs": 250, "Buffalo Bills": 350, "Baltimore Ravens": 500,
             "Houston Texans": 700, "Cincinnati Bengals": 900, "Miami Dolphins": 1000,
             "Pittsburgh Steelers": 1200, "Cleveland Browns": 1800, "New York Jets": 2000,
             "Denver Broncos": 2500, "Jacksonville Jaguars": 1600, "Las Vegas Raiders": 5000}),
        _demo_futures_event(
            "demo_nfl_nfc", "americanfootball_nfl_nfc_conference_winner", "NFC Champion", "nfl",
            "2027-01-25T00:00:00Z",
            {"Detroit Lions": 300, "Philadelphia Eagles": 400, "San Francisco 49ers": 550,
             "Green Bay Packers": 650, "Dallas Cowboys": 800, "Minnesota Vikings": 1200,
             "Los Angeles Rams": 1400, "Atlanta Falcons": 2000, "Seattle Seahawks": 2500,
             "Chicago Bears": 3000, "Tampa Bay Buccaneers": 3500, "New York Giants": 8000}),
    ]


def _get_demo_ncaab_events() -> list[dict]:
    return [
        _demo_futures_event(
            "demo_ncaab_champ", "basketball_ncaab_championship_winner", "NCAAB Championship", "ncaab",
            "2027-04-07T00:00:00Z",
            {"Duke": 500, "Houston": 600, "UConn": 700, "Kansas": 800,
             "Auburn": 1000, "Purdue": 1200, "Tennessee": 1400, "Arizona": 1600,
             "Gonzaga": 1800, "North Carolina": 2000, "Kentucky": 2200,
             "Marquette": 2500, "Baylor": 3000, "Creighton": 3500,
             "Iowa State": 4000, "Texas": 4500, "Alabama": 5000,
             "St. John's": 6000, "Michigan State": 6500, "UCLA": 7000}),
    ]


def _get_demo_ncaaf_events() -> list[dict]:
    return [
        _demo_futures_event(
            "demo_ncaaf_champ", "americanfootball_ncaaf_championship_winner", "CFP National Championship", "ncaaf",
            "2027-01-20T00:00:00Z",
            {"Georgia": 350, "Ohio State": 500, "Texas": 600, "Oregon": 700,
             "Alabama": 800, "Michigan": 1000, "Penn State": 1200, "USC": 1400,
             "Notre Dame": 1600, "Clemson": 1800, "Florida State": 2000,
             "LSU": 2200, "Oklahoma": 2500, "Tennessee": 2800,
             "Ole Miss": 3000, "Miami (FL)": 3500, "Utah": 4000,
             "Washington": 4500, "Colorado": 5000, "Iowa": 8000}),
    ]


def _demo_futures_event(event_id: str, sport_key: str, title: str, group: str,
                         commence: str, teams_base: dict) -> dict:
    """Generate a demo futures event with bookmaker disagreement."""
    book_offsets = {
        "fanduel": {},
        "draftkings": {k: (-50 if i % 4 == 0 else 100 if i % 5 == 2 else 0) for i, k in enumerate(teams_base)},
        "betmgm": {k: (200 if i % 3 == 0 else -100 if i % 6 == 1 else 0) for i, k in enumerate(teams_base)},
        "caesars": {k: (150 if i % 4 == 2 else 0) for i, k in enumerate(teams_base)},
        "espnbet": {k: (300 if i % 5 == 0 else 0) for i, k in enumerate(teams_base)},
        "pinnacle": {k: (-20 if i < 3 else 0) for i, k in enumerate(teams_base)},
        "lowvig": {k: (-15 if i < 2 else 0) for i, k in enumerate(teams_base)},
    }
    bookmakers = []
    for book_key, offsets in book_offsets.items():
        outcomes = [{"name": t, "price": max(teams_base[t] + offsets.get(t, 0), 100)} for t in teams_base]
        bookmakers.append({"key": book_key, "title": BOOK_DISPLAY_NAMES.get(book_key, book_key),
                           "markets": [{"key": "outrights", "outcomes": outcomes}]})
    return {
        "id": event_id, "_sport_key": sport_key, "_sport_title": title,
        "_sport_group": group, "commence_time": commence, "bookmakers": bookmakers,
    }
