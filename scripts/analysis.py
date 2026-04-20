"""
Offsides Report - Multi-Event Analysis Pipeline

Analyzes ALL active golf events and markets, outputting
structured JSON for each event.
"""

from datetime import datetime
from typing import Optional

from ev_engine import (
    american_to_decimal,
    decimal_to_implied_prob,
    calculate_consensus_probabilities,
    calculate_ev_percentage,
    classify_value,
    kelly_fraction,
    detect_odds_outliers,
    calculate_market_vig,
    minimum_edge_threshold,
    decimal_to_american,
)
from odds_fetcher import fetch_all_golf_odds, parse_event_odds
from analytics import (
    fetch_datagolf_rankings,
    get_analytics_for_player,
    get_course_fit_summary,
    get_form_summary,
    get_trending_players,
    get_heating_up,
)
from config import (
    NC_BOOKS,
    SHARP_REFERENCE_BOOKS,
    BOOK_DISPLAY_NAMES,
    RISK_FREE_RATE,
    BASE_EDGE_MINIMUM,
    MARKET_DISPLAY_NAMES,
)


def analyze_outright_market(market_data: dict, market_key: str,
                            days_to_resolution: int, dg_rankings: list) -> dict:
    """
    Run EV analysis on an outright-style market (winner, top 5, top 10, etc.)
    Returns structured analysis ready for JSON output.
    """
    outcomes_by_book = market_data.get("outcomes_by_book", {})
    odds_by_book = market_data.get("odds_by_book", {})
    decimal_odds_by_book = market_data.get("decimal_odds_by_book", {})

    if not outcomes_by_book:
        return {"error": "No odds data for this market"}

    # Calculate vig per book
    book_vigs = {}
    for book, probs in outcomes_by_book.items():
        vig = calculate_market_vig(list(probs.values()))
        book_vigs[book] = vig

    # Build consensus from sharp books if available
    available_sharp = [b for b in SHARP_REFERENCE_BOOKS if b in outcomes_by_book]
    available_nc = [b for b in NC_BOOKS if b in outcomes_by_book]

    if available_sharp:
        consensus = calculate_consensus_probabilities(
            outcomes_by_book, method="power", sharp_books=available_sharp)
    else:
        consensus = calculate_consensus_probabilities(
            outcomes_by_book, method="power", vig_weight=True)

    # Calculate minimum edge threshold
    min_edge = minimum_edge_threshold(days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)

    # Find value selections (NC-legal books only)
    value_selections = []
    for player in sorted(consensus.keys()):
        true_prob = consensus[player]
        analytics = get_analytics_for_player(player, dg_rankings)

        for book in available_nc:
            if player not in decimal_odds_by_book.get(book, {}):
                continue

            offered_decimal = decimal_odds_by_book[book][player]
            offered_american = odds_by_book[book].get(player, 0)
            ev_pct = calculate_ev_percentage(offered_decimal, true_prob)
            value_tier = classify_value(ev_pct, days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)
            kelly = kelly_fraction(offered_decimal, true_prob)

            fair_decimal = 1.0 / true_prob if true_prob > 0 else float("inf")
            fair_american = decimal_to_american(fair_decimal) if true_prob > 0 else 0

            entry = {
                "player": player,
                "book": book,
                "book_display": BOOK_DISPLAY_NAMES.get(book, book),
                "american_odds": offered_american,
                "decimal_odds": round(offered_decimal, 3),
                "fair_american": fair_american,
                "implied_prob": round(decimal_to_implied_prob(offered_decimal), 5),
                "true_prob": round(true_prob, 5),
                "ev_pct": round(ev_pct, 2),
                "value_tier": value_tier,
                "kelly_pct": round(kelly * 100, 2),
                "analytics": _serialize_analytics(analytics),
            }

            if value_tier:
                value_selections.append(entry)

    value_selections.sort(key=lambda x: x["ev_pct"], reverse=True)
    strong_picks = [v for v in value_selections if v["value_tier"] == "STRONG VALUE"]
    notable_picks = [v for v in value_selections if v["value_tier"] == "Notable Value"]

    # Build odds comparison table (top 20 by consensus prob, NC books only)
    top_players = sorted(consensus.items(), key=lambda x: x[1], reverse=True)[:20]
    odds_table = []
    for player, true_prob in top_players:
        row = {
            "player": player,
            "true_prob": round(true_prob, 5),
            "fair_american": decimal_to_american(1.0 / true_prob) if true_prob > 0 else 0,
            "analytics": _serialize_analytics(get_analytics_for_player(player, dg_rankings)),
            "books": {},
        }
        best_odds = 0
        best_book = None
        for book in odds_by_book:
            if book not in NC_BOOKS:
                continue
            if player in odds_by_book[book]:
                am = odds_by_book[book][player]
                dec = decimal_odds_by_book[book][player]
                ev = calculate_ev_percentage(dec, true_prob)
                row["books"][book] = {
                    "american": am,
                    "decimal": round(dec, 3),
                    "ev_pct": round(ev, 2),
                }
                if dec > best_odds:
                    best_odds = dec
                    best_book = book
        row["best_book"] = best_book
        row["best_book_display"] = BOOK_DISPLAY_NAMES.get(best_book, "") if best_book else ""
        odds_table.append(row)

    # Detect outliers
    outlier_summary = []
    for player in consensus.keys():
        player_odds_all = {}
        for book, od in decimal_odds_by_book.items():
            if player in od:
                player_odds_all[book] = od[player]
        outliers = detect_odds_outliers(player_odds_all, threshold_pct=15.0)
        for o in outliers:
            if o["book"] not in NC_BOOKS:
                continue
            o["player"] = player
            o["book_display"] = BOOK_DISPLAY_NAMES.get(o["book"], o["book"])
            outlier_summary.append(o)
    outlier_summary.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)

    return {
        "market_key": market_key,
        "market_name": MARKET_DISPLAY_NAMES.get(market_key, market_key),
        "num_books": len(outcomes_by_book),
        "num_nc_books": len(available_nc),
        "num_sharp_books": len(available_sharp),
        "num_players": len(consensus),
        "min_edge_threshold": round(min_edge * 100, 2),
        "strong_picks": strong_picks[:25],
        "notable_picks": notable_picks[:25],
        "all_value_count": len(value_selections),
        "odds_table": odds_table,
        "outlier_summary": outlier_summary[:15],
        "book_vigs": {BOOK_DISPLAY_NAMES.get(k, k): round(v * 100, 1) for k, v in book_vigs.items()},
        "nc_books_available": [BOOK_DISPLAY_NAMES.get(b, b) for b in available_nc],
        "sharp_books_available": [BOOK_DISPLAY_NAMES.get(b, b) for b in available_sharp],
    }


def analyze_h2h_market(market_data: dict, days_to_resolution: int, dg_rankings: list) -> dict:
    """
    Analyze head-to-head matchup market.
    Each matchup is a two-outcome market with its own EV calculation.
    """
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    matchups_by_book = market_data.get("matchups_by_book", {})
    if not matchups_by_book:
        return {"error": "No matchup data"}

    min_edge = minimum_edge_threshold(days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)

    # Aggregate matchups across books
    # Key: (player_a, player_b) -> {book: {a_price, b_price}}
    matchup_index = {}
    for book, matchups in matchups_by_book.items():
        for m in matchups:
            key = (m["player_a"], m["player_b"])
            if key not in matchup_index:
                matchup_index[key] = {}
            matchup_index[key][book] = {
                "price_a": m["price_a"],
                "price_b": m["price_b"],
            }

    analyzed_matchups = []
    for (player_a, player_b), books_data in matchup_index.items():
        # Calculate consensus probability for this matchup
        all_prob_a = []
        all_prob_b = []
        for book, prices in books_data.items():
            dec_a = american_to_decimal(prices["price_a"])
            dec_b = american_to_decimal(prices["price_b"])
            imp_a = decimal_to_implied_prob(dec_a)
            imp_b = decimal_to_implied_prob(dec_b)
            # Normalize the pair
            total = imp_a + imp_b
            if total > 0:
                # Weight sharp books more
                weight = 2.0 if book in SHARP_REFERENCE_BOOKS else 1.0
                all_prob_a.append((imp_a / total, weight))
                all_prob_b.append((imp_b / total, weight))

        if not all_prob_a:
            continue

        # Weighted average consensus
        total_weight = sum(w for _, w in all_prob_a)
        true_prob_a = sum(p * w for p, w in all_prob_a) / total_weight
        true_prob_b = 1.0 - true_prob_a

        # Find value at NC-legal books
        matchup_picks = []
        for book, prices in books_data.items():
            if book not in NC_BOOKS:
                continue

            for player, price, true_prob in [
                (player_a, prices["price_a"], true_prob_a),
                (player_b, prices["price_b"], true_prob_b),
            ]:
                dec = american_to_decimal(price)
                ev_pct = calculate_ev_percentage(dec, true_prob)
                value_tier = classify_value(ev_pct, days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)

                if value_tier:
                    matchup_picks.append({
                        "player": player,
                        "opponent": player_b if player == player_a else player_a,
                        "book": book,
                        "book_display": BOOK_DISPLAY_NAMES.get(book, book),
                        "american_odds": price,
                        "true_prob": round(true_prob, 4),
                        "ev_pct": round(ev_pct, 2),
                        "value_tier": value_tier,
                        "analytics": _serialize_analytics(
                            get_analytics_for_player(player, dg_rankings)),
                    })

        # Build comparison row
        book_odds = {}
        for book, prices in books_data.items():
            if book not in NC_BOOKS:
                continue
            book_odds[BOOK_DISPLAY_NAMES.get(book, book)] = {
                "player_a_odds": prices["price_a"],
                "player_b_odds": prices["price_b"],
            }

        analyzed_matchups.append({
            "player_a": player_a,
            "player_b": player_b,
            "true_prob_a": round(true_prob_a, 4),
            "true_prob_b": round(true_prob_b, 4),
            "book_odds": book_odds,
            "value_picks": matchup_picks,
            "analytics_a": _serialize_analytics(get_analytics_for_player(player_a, dg_rankings)),
            "analytics_b": _serialize_analytics(get_analytics_for_player(player_b, dg_rankings)),
        })

    # Sort by total value found
    analyzed_matchups.sort(key=lambda x: len(x["value_picks"]), reverse=True)

    all_picks = []
    for m in analyzed_matchups:
        all_picks.extend(m["value_picks"])
    all_picks.sort(key=lambda x: x["ev_pct"], reverse=True)

    return {
        "market_key": "h2h",
        "market_name": "Head-to-Head Matchups",
        "num_matchups": len(analyzed_matchups),
        "min_edge_threshold": round(min_edge * 100, 2),
        "matchups": analyzed_matchups,
        "strong_picks": [p for p in all_picks if p["value_tier"] == "STRONG VALUE"][:15],
        "notable_picks": [p for p in all_picks if p["value_tier"] == "Notable Value"][:15],
    }


def run_full_analysis(api_key: str = "") -> list[dict]:
    """
    Run analysis on ALL active golf events.
    Returns a list of event reports, each containing analysis for every available market.
    """
    print("=" * 60)
    print("  THE OFFSIDES REPORT — Full Golf Analysis")
    print(f"  {datetime.now().strftime('%A, %B %d, %Y %H:%M')}")
    print("=" * 60)

    # Fetch analytics (same for all events)
    print("\n  Loading DataGolf analytics...")
    dg_rankings = fetch_datagolf_rankings()
    course_fit_leaders = get_course_fit_summary(dg_rankings)
    form_leaders = get_form_summary(dg_rankings)
    trending_players = get_trending_players(dg_rankings)
    heating_up = get_heating_up(dg_rankings, min_rank_jump=5)

    # Fetch all events
    print("\n  Fetching odds for all active golf events...")
    raw_events = fetch_all_golf_odds(api_key)
    print(f"  Retrieved {len(raw_events)} events")

    event_reports = []

    for raw_event in raw_events:
        parsed = parse_event_odds(raw_event)
        event_name = parsed["event_name"]
        sport_key = parsed["sport_key"]
        event_date = parsed["event_date"]

        print(f"\n{'─' * 50}")
        print(f"  Analyzing: {event_name}")
        print(f"  Sport key: {sport_key}")

        # Calculate days to resolution
        days_to_resolution = 4  # default
        if event_date:
            try:
                event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                days_to_resolution = max(1, (event_dt - datetime.now(event_dt.tzinfo)).days)
            except Exception:
                pass

        print(f"  Days to resolution: {days_to_resolution}")

        event_report = {
            "event_id": parsed["event_id"],
            "event_name": event_name,
            "sport_key": sport_key,
            "event_date": event_date,
            "days_to_resolution": days_to_resolution,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "markets": {},
            "analytics": {
                "course_fit_leaders": [_serialize_analytics(p) for p in course_fit_leaders],
                "form_leaders": [_serialize_analytics(p) for p in form_leaders],
                "trending_players": [_serialize_analytics(p) for p in trending_players],
                "heating_up": [_serialize_analytics(p) for p in heating_up],
            },
        }

        # Analyze each available market
        for market_key, market_data in parsed["markets"].items():
            if market_key == "h2h":
                print(f"  Analyzing H2H matchups...")
                event_report["markets"]["h2h"] = analyze_h2h_market(
                    market_data, days_to_resolution, dg_rankings)
            else:
                print(f"  Analyzing {MARKET_DISPLAY_NAMES.get(market_key, market_key)}...")
                event_report["markets"][market_key] = analyze_outright_market(
                    market_data, market_key, days_to_resolution, dg_rankings)

        # Summary
        for mk, md in event_report["markets"].items():
            if "error" in md:
                continue
            strong = len(md.get("strong_picks", []))
            notable = len(md.get("notable_picks", []))
            print(f"    {MARKET_DISPLAY_NAMES.get(mk, mk)}: {strong} strong, {notable} notable picks")

        event_reports.append(event_report)

    print(f"\n{'=' * 60}")
    print(f"  Analysis complete: {len(event_reports)} events processed")
    print(f"{'=' * 60}")

    return event_reports


def _serialize_analytics(analytics) -> Optional[dict]:
    """Ensure analytics data is JSON-serializable."""
    if analytics is None:
        return None
    return {k: v for k, v in analytics.items() if k != "_raw"}
