"""
Offsides Report - Multi-Sport Analysis Pipeline

Analyzes ALL active events across golf, NBA, NCAAB, NFL, NCAAF.
The EV engine is sport-agnostic — same math works for golfers,
teams, conferences, etc.
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
from odds_fetcher import fetch_all_odds, parse_event_odds
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
    SPORT_GROUPS,
)


def analyze_outright_market(market_data: dict, market_key: str,
                            days_to_resolution: int, dg_rankings: list = None) -> dict:
    """
    Run EV analysis on an outright-style market.
    Works for any sport: golf winner, NBA champion, Super Bowl, etc.
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

    min_edge = minimum_edge_threshold(days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)

    # Find value selections (NC-legal books only)
    value_selections = []
    for outcome in sorted(consensus.keys()):
        true_prob = consensus[outcome]

        # Golf analytics overlay (only for golf)
        analytics = None
        if dg_rankings:
            analytics = get_analytics_for_player(outcome, dg_rankings)

        for book in available_nc:
            if outcome not in decimal_odds_by_book.get(book, {}):
                continue

            offered_decimal = decimal_odds_by_book[book][outcome]
            offered_american = odds_by_book[book].get(outcome, 0)
            ev_pct = calculate_ev_percentage(offered_decimal, true_prob)
            value_tier = classify_value(ev_pct, days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)
            kelly = kelly_fraction(offered_decimal, true_prob)

            fair_decimal = 1.0 / true_prob if true_prob > 0 else float("inf")
            fair_american = decimal_to_american(fair_decimal) if true_prob > 0 else 0

            entry = {
                "player": outcome,
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

    # Odds comparison table (top 100 by consensus prob, NC books only)
    top_outcomes = sorted(consensus.items(), key=lambda x: x[1], reverse=True)[:100]
    odds_table = []
    for outcome, true_prob in top_outcomes:
        analytics = None
        if dg_rankings:
            analytics = get_analytics_for_player(outcome, dg_rankings)

        row = {
            "player": outcome,
            "true_prob": round(true_prob, 5),
            "fair_american": decimal_to_american(1.0 / true_prob) if true_prob > 0 else 0,
            "analytics": _serialize_analytics(analytics),
            "books": {},
        }
        best_odds = 0
        best_book = None
        for book in odds_by_book:
            if book not in NC_BOOKS:
                continue
            if outcome in odds_by_book[book]:
                am = odds_by_book[book][outcome]
                dec = decimal_odds_by_book[book][outcome]
                ev = calculate_ev_percentage(dec, true_prob)
                row["books"][book] = {
                    "american": am,
                    "decimal": round(dec, 3),
                    "ev_pct": round(ev, 2),
                }
                # Track best odds = highest decimal (best price for bettor)
                if dec > best_odds:
                    best_odds = dec
                    best_book = book
        row["best_book"] = best_book
        row["best_book_display"] = BOOK_DISPLAY_NAMES.get(best_book, "") if best_book else ""
        odds_table.append(row)

    # Detect outliers
    outlier_summary = []
    for outcome in consensus.keys():
        outcome_odds_all = {}
        for book, od in decimal_odds_by_book.items():
            if outcome in od:
                outcome_odds_all[book] = od[outcome]
        outliers = detect_odds_outliers(outcome_odds_all, threshold_pct=15.0)
        for o in outliers:
            if o["book"] not in NC_BOOKS:
                continue
            o["player"] = outcome
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


def analyze_h2h_market(market_data: dict, days_to_resolution: int, dg_rankings: list = None) -> dict:
    """Analyze golf-style head-to-head matchup market."""
    from ev_engine import american_to_decimal, decimal_to_implied_prob

    matchups_by_book = market_data.get("matchups_by_book", {})
    if not matchups_by_book:
        return {"error": "No matchup data"}

    min_edge = minimum_edge_threshold(days_to_resolution, RISK_FREE_RATE, BASE_EDGE_MINIMUM)

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
        all_prob_a = []
        for book, prices in books_data.items():
            dec_a = american_to_decimal(prices["price_a"])
            dec_b = american_to_decimal(prices["price_b"])
            imp_a = decimal_to_implied_prob(dec_a)
            imp_b = decimal_to_implied_prob(dec_b)
            total = imp_a + imp_b
            if total > 0:
                weight = 2.0 if book in SHARP_REFERENCE_BOOKS else 1.0
                all_prob_a.append((imp_a / total, weight))

        if not all_prob_a:
            continue

        total_weight = sum(w for _, w in all_prob_a)
        true_prob_a = sum(p * w for p, w in all_prob_a) / total_weight
        true_prob_b = 1.0 - true_prob_a

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
                            get_analytics_for_player(player, dg_rankings) if dg_rankings else None),
                    })

        book_odds = {}
        for book, prices in books_data.items():
            if book not in NC_BOOKS:
                continue
            book_odds[BOOK_DISPLAY_NAMES.get(book, book)] = {
                "player_a_odds": prices["price_a"],
                "player_b_odds": prices["price_b"],
            }

        analyzed_matchups.append({
            "player_a": player_a, "player_b": player_b,
            "true_prob_a": round(true_prob_a, 4),
            "true_prob_b": round(true_prob_b, 4),
            "book_odds": book_odds,
            "value_picks": matchup_picks,
        })

    analyzed_matchups.sort(key=lambda x: len(x["value_picks"]), reverse=True)
    all_picks = [p for m in analyzed_matchups for p in m["value_picks"]]
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


def run_full_analysis(api_key: str = "") -> dict[str, list[dict]]:
    """
    Run analysis on ALL active events across all sports.
    Returns: {sport_group: [event_reports]}
    """
    print("=" * 60)
    print("  THE OFFSIDES REPORT — Full Multi-Sport Analysis")
    print(f"  {datetime.now().strftime('%A, %B %d, %Y %H:%M')}")
    print("=" * 60)

    # Golf analytics (only applies to golf events)
    print("\n  Loading DataGolf analytics...")
    dg_rankings = fetch_datagolf_rankings()
    golf_analytics = {
        "course_fit_leaders": [_serialize_analytics(p) for p in get_course_fit_summary(dg_rankings)],
        "form_leaders": [_serialize_analytics(p) for p in get_form_summary(dg_rankings)],
        "trending_players": [_serialize_analytics(p) for p in get_trending_players(dg_rankings)],
        "heating_up": [_serialize_analytics(p) for p in get_heating_up(dg_rankings, min_rank_jump=5)],
    }

    # Fetch all odds
    print("\n  Fetching odds for all active sports...")
    raw_by_group = fetch_all_odds(api_key)

    total_events = sum(len(events) for events in raw_by_group.values())
    print(f"  Retrieved {total_events} events across {len(raw_by_group)} sports")

    results = {}

    for group_key, raw_events in raw_by_group.items():
        group_cfg = SPORT_GROUPS.get(group_key, {})
        group_name = group_cfg.get("display_name", group_key)
        is_golf = group_key == "golf"

        print(f"\n{'━' * 50}")
        print(f"  {group_cfg.get('icon', '')} {group_name} ({len(raw_events)} events)")
        print(f"{'━' * 50}")

        results[group_key] = []

        for raw_event in raw_events:
            parsed = parse_event_odds(raw_event)
            event_name = parsed["event_name"]

            # Calculate days to resolution
            days_to_resolution = group_cfg.get("typical_resolution_days", 30)
            if parsed["event_date"]:
                try:
                    event_dt = datetime.fromisoformat(parsed["event_date"].replace("Z", "+00:00"))
                    days_to_resolution = max(1, (event_dt - datetime.now(event_dt.tzinfo)).days)
                except Exception:
                    pass

            print(f"\n  {event_name} ({days_to_resolution}d)")

            event_report = {
                "event_id": parsed["event_id"],
                "event_name": event_name,
                "sport_key": parsed["sport_key"],
                "sport_group": group_key,
                "event_date": parsed["event_date"],
                "days_to_resolution": days_to_resolution,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "markets": {},
                "analytics": golf_analytics if is_golf else None,
            }

            for market_key, market_data in parsed["markets"].items():
                if market_key == "h2h" and "matchups_by_book" in market_data:
                    event_report["markets"]["h2h"] = analyze_h2h_market(
                        market_data, days_to_resolution, dg_rankings if is_golf else None)
                else:
                    event_report["markets"][market_key] = analyze_outright_market(
                        market_data, market_key, days_to_resolution,
                        dg_rankings if is_golf else None)

            for mk, md in event_report["markets"].items():
                if "error" in md:
                    continue
                s = len(md.get("strong_picks", []))
                n = len(md.get("notable_picks", []))
                print(f"    {MARKET_DISPLAY_NAMES.get(mk, mk)}: {s} strong, {n} notable")

            results[group_key].append(event_report)

    total_processed = sum(len(v) for v in results.values())
    print(f"\n{'=' * 60}")
    print(f"  Analysis complete: {total_processed} events across {len(results)} sports")
    print(f"{'=' * 60}")

    return results


def _serialize_analytics(analytics) -> Optional[dict]:
    if analytics is None:
        return None
    return {k: v for k, v in analytics.items() if k != "_raw"}
