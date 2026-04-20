"""
Offsides Report - Odds Data Fetcher (Multi-Event)

Fetches odds from The Odds API for ALL active golf events.
Supports outrights, h2h, top 5/10/20 markets.
Optimized for free tier (500 requests/month).
"""

import json
import os
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import ODDS_API_KEY, ODDS_API_BASE, BOOK_DISPLAY_NAMES, GOLF_MARKETS


def fetch_available_golf_sports(api_key: str) -> list[dict]:
    """
    Discover which golf sport keys are currently active.
    Golf uses per-tournament keys like 'golf_masters_tournament_winner'.
    Costs 1 API request.
    """
    url = f"{ODDS_API_BASE}/sports"
    params = {"apiKey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  API requests remaining: {remaining}")
        all_sports = resp.json()
        golf_sports = [
            s for s in all_sports
            if s.get("active", False) and (
                "golf" in s.get("group", "").lower()
                or "golf" in s.get("key", "").lower()
            )
        ]
        return golf_sports
    except Exception as e:
        print(f"  API error fetching sports: {e}")
        return []


def fetch_all_golf_odds(api_key: str, markets: str = GOLF_MARKETS) -> list[dict]:
    """
    Fetch odds for ALL active golf events in one sweep.

    Strategy to minimize API usage:
    1. One call to /sports to discover active golf events
    2. One call per event with ALL markets combined

    Returns list of event dicts, each containing:
    - event metadata (name, date, sport_key)
    - raw bookmaker odds for all requested markets
    """
    if not api_key:
        print("  No API key — using demo data")
        return get_demo_all_events()

    # Step 1: Discover active golf events
    print("\n  Discovering active golf events...")
    golf_sports = fetch_available_golf_sports(api_key)

    if not golf_sports:
        print("  No active golf events found — using demo data")
        return get_demo_all_events()

    print(f"  Found {len(golf_sports)} active golf markets:")
    for s in golf_sports:
        print(f"    - {s['key']}: {s.get('title', 'Unknown')}")

    # Step 2: Fetch odds for each event (one API call each, all markets)
    all_events = []
    for sport in golf_sports:
        sport_key = sport["key"]
        sport_title = sport.get("title", sport_key)

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
                    event["_sport_title"] = sport_title
                    all_events.append(event)
            elif isinstance(data, dict) and "bookmakers" in data:
                data["_sport_key"] = sport_key
                data["_sport_title"] = sport_title
                all_events.append(data)
        except Exception as e:
            print(f"  {sport_key}: error — {e}")

    if not all_events:
        print("  No odds data retrieved — using demo data")
        return get_demo_all_events()

    return all_events


def parse_event_odds(event: dict) -> dict:
    """
    Parse a single event's odds into our internal format.
    Handles multiple market types (outrights, h2h, top_5, etc.)

    Returns:
        {
            "event_id": str,
            "event_name": str,
            "sport_key": str,
            "event_date": str,
            "markets": {
                "outrights": {
                    "outcomes_by_book": {...},
                    "odds_by_book": {...},
                    "decimal_odds_by_book": {...},
                },
                "h2h": {
                    "matchups": [
                        {
                            "player_a": str,
                            "player_b": str,
                            "odds_by_book": {...}
                        }
                    ]
                },
                ...
            }
        }
    """
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    result = {
        "event_id": event.get("id", "unknown"),
        "event_name": event.get("_sport_title", event.get("sport_title", "Golf Event")),
        "sport_key": event.get("_sport_key", event.get("sport_key", "golf")),
        "event_date": event.get("commence_time", ""),
        "markets": {},
    }

    bookmakers = event.get("bookmakers", [])

    # Group outcomes by market type
    for bm in bookmakers:
        book_key = bm.get("key", "unknown")

        for market in bm.get("markets", []):
            market_key = market.get("key", "unknown")

            if market_key == "h2h":
                # Head-to-head matchups: pairs of outcomes
                _parse_h2h_market(result, market, book_key)
            elif market_key in ("outrights", "top_5", "top_10", "top_20"):
                # Standard outright-style markets
                _parse_outright_market(result, market, market_key, book_key)

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


def _parse_h2h_market(result: dict, market: dict, book_key: str):
    """Parse head-to-head matchup market into structured matchup pairs."""
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    if "h2h" not in result["markets"]:
        result["markets"]["h2h"] = {"matchups_by_book": {}}

    outcomes = market.get("outcomes", [])
    if len(outcomes) < 2:
        return

    # H2H markets come as pairs: outcomes[0] vs outcomes[1], etc.
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


# ── Demo Data ─────────────────────────────────────────────────

def get_demo_all_events() -> list[dict]:
    """Return demo data simulating multiple active golf events."""
    today = datetime.now()
    thursday = today + timedelta(days=(3 - today.weekday()) % 7)

    return [
        # Current week tournament
        {
            "id": "demo_zurich_classic_2026",
            "_sport_key": "golf_pga_tour_zurich_classic",
            "_sport_title": "Zurich Classic of New Orleans",
            "sport_key": "golf_pga_tour",
            "sport_title": "Zurich Classic of New Orleans",
            "commence_time": thursday.strftime("%Y-%m-%dT13:00:00Z"),
            "bookmakers": _demo_current_week_bookmakers(),
        },
        # PGA Championship futures
        {
            "id": "demo_pga_championship_2026",
            "_sport_key": "golf_pga_championship_winner",
            "_sport_title": "PGA Championship Winner",
            "sport_key": "golf_pga_championship_winner",
            "sport_title": "PGA Championship Winner",
            "commence_time": "2026-05-14T13:00:00Z",
            "bookmakers": _demo_futures_bookmakers("PGA Championship"),
        },
        # US Open futures
        {
            "id": "demo_us_open_2026",
            "_sport_key": "golf_us_open_winner",
            "_sport_title": "US Open Winner",
            "sport_key": "golf_us_open_winner",
            "sport_title": "US Open Winner",
            "commence_time": "2026-06-18T13:00:00Z",
            "bookmakers": _demo_futures_bookmakers("US Open"),
        },
        # The Open Championship futures
        {
            "id": "demo_the_open_2026",
            "_sport_key": "golf_the_open_championship_winner",
            "_sport_title": "The Open Championship Winner",
            "sport_key": "golf_the_open_championship_winner",
            "sport_title": "The Open Championship Winner",
            "commence_time": "2026-07-16T13:00:00Z",
            "bookmakers": _demo_futures_bookmakers("The Open"),
        },
    ]


def _demo_current_week_bookmakers() -> list:
    """Demo bookmaker data for current week event."""
    players_base = {
        "Scottie Scheffler": 650, "Collin Morikawa": 1400,
        "Xander Schauffele": 1100, "Rory McIlroy": 1200,
        "Patrick Cantlay": 1800, "Matt Fitzpatrick": 2200,
        "Shane Lowry": 2500, "Justin Thomas": 2000,
        "Tommy Fleetwood": 2800, "Hideki Matsuyama": 1600,
        "Viktor Hovland": 2000, "Cameron Young": 3500,
        "Corey Conners": 3000, "Sahith Theegala": 2500,
        "Wyndham Clark": 2200, "Tom Kim": 3000,
        "Russell Henley": 4000, "Brian Harman": 4500,
        "Denny McCarthy": 5000, "Akshay Bhatia": 4000,
        "Sepp Straka": 5500, "Keegan Bradley": 5000,
        "Sungjae Im": 3500, "Davis Thompson": 6000,
        "Max Homa": 4000,
    }

    # Offsets to simulate book disagreement (value spots)
    book_offsets = {
        "fanduel": {},
        "draftkings": {"Collin Morikawa": -200, "Rory McIlroy": 200, "Viktor Hovland": -200},
        "betmgm": {"Collin Morikawa": 200, "Shane Lowry": 800, "Cameron Young": 500, "Sepp Straka": 1000},
        "caesars": {"Justin Thomas": 500, "Brian Harman": 1000, "Max Homa": 1000},
        "espnbet": {"Tommy Fleetwood": 700, "Denny McCarthy": 1000},
        "pinnacle": {"Scottie Scheffler": -50, "Collin Morikawa": -100},
        "lowvig": {"Scottie Scheffler": -30, "Xander Schauffele": -50},
    }

    bookmakers = []
    for book_key, offsets in book_offsets.items():
        outcomes = []
        for player, base_price in players_base.items():
            price = base_price + offsets.get(player, 0)
            outcomes.append({"name": player, "price": price})

        markets = [{"key": "outrights", "outcomes": outcomes}]

        # Add h2h matchups for some books
        if book_key in ("fanduel", "draftkings", "betmgm", "caesars"):
            h2h_outcomes = [
                {"name": "Scottie Scheffler", "price": -130},
                {"name": "Xander Schauffele", "price": 110},
                {"name": "Rory McIlroy", "price": -110},
                {"name": "Collin Morikawa", "price": -110},
                {"name": "Patrick Cantlay", "price": 140},
                {"name": "Viktor Hovland", "price": -160},
            ]
            # Vary h2h odds slightly by book
            if book_key == "draftkings":
                h2h_outcomes[0]["price"] = -140
                h2h_outcomes[1]["price"] = 120
            elif book_key == "betmgm":
                h2h_outcomes[2]["price"] = -105
                h2h_outcomes[3]["price"] = -115

            markets.append({"key": "h2h", "outcomes": h2h_outcomes})

        bookmakers.append({
            "key": book_key,
            "title": BOOK_DISPLAY_NAMES.get(book_key, book_key),
            "markets": markets,
        })

    return bookmakers


def _demo_futures_bookmakers(tournament: str) -> list:
    """Demo bookmaker data for futures markets with tournament-specific offsets."""
    players_base = {
        "Scottie Scheffler": 500, "Xander Schauffele": 900,
        "Rory McIlroy": 1000, "Collin Morikawa": 1200,
        "Hideki Matsuyama": 1800, "Patrick Cantlay": 2000,
        "Viktor Hovland": 2200, "Sahith Theegala": 2500,
        "Wyndham Clark": 2500, "Matt Fitzpatrick": 2800,
        "Justin Thomas": 2500, "Tommy Fleetwood": 3000,
        "Shane Lowry": 3000, "Tom Kim": 3500,
        "Cameron Young": 4000, "Corey Conners": 4000,
        "Sungjae Im": 4500, "Akshay Bhatia": 4000,
        "Brian Harman": 5000, "Russell Henley": 5000,
        "Keegan Bradley": 5500, "Denny McCarthy": 6000,
        "Max Homa": 5000, "Sepp Straka": 6000,
        "Davis Thompson": 7000,
    }

    # Tournament-specific adjustments
    tourney_adjust = {
        "PGA Championship": {"Xander Schauffele": -100, "Rory McIlroy": -200, "Justin Thomas": -300},
        "US Open": {"Matt Fitzpatrick": -500, "Wyndham Clark": -300, "Scottie Scheffler": -100},
        "The Open": {"Rory McIlroy": -300, "Shane Lowry": -500, "Tommy Fleetwood": -500},
    }

    adjustments = tourney_adjust.get(tournament, {})

    book_offsets = {
        "fanduel": {},
        "draftkings": {"Scottie Scheffler": -50, "Rory McIlroy": 200},
        "betmgm": {"Collin Morikawa": 300, "Cameron Young": 500, "Sepp Straka": 1000},
        "caesars": {"Justin Thomas": 500, "Brian Harman": 1500},
        "espnbet": {"Tommy Fleetwood": 500, "Denny McCarthy": 1000},
        "pinnacle": {"Scottie Scheffler": -30},
        "lowvig": {"Xander Schauffele": -50},
    }

    bookmakers = []
    for book_key, offsets in book_offsets.items():
        outcomes = []
        for player, base_price in players_base.items():
            price = base_price + adjustments.get(player, 0) + offsets.get(player, 0)
            price = max(price, 100)  # Floor at +100
            outcomes.append({"name": player, "price": price})
        bookmakers.append({
            "key": book_key,
            "title": BOOK_DISPLAY_NAMES.get(book_key, book_key),
            "markets": [{"key": "outrights", "outcomes": outcomes}],
        })

    return bookmakers
