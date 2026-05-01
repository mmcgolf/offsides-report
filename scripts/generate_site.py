#!/usr/bin/env python3
"""
Offsides Report - Multi-Sport Static Site Generator

Runs the full analysis pipeline across all sports and outputs
JSON data files for the static site. Designed to run in GitHub Actions.

Usage:
    python generate_site.py              # Uses demo data
    python generate_site.py --live       # Uses live API (requires ODDS_API_KEY env var)
"""

import json
import os
import sys
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from analysis import run_full_analysis
from config import (
    ODDS_API_KEY,
    NEWSLETTER_NAME,
    NEWSLETTER_TAGLINE,
    RISK_FREE_RATE,
    BASE_EDGE_MINIMUM,
    MARKET_DISPLAY_NAMES,
    SPORT_GROUPS,
    SPORT_KEY_DISPLAY,
)


def generate_site_data(api_key: str = "", output_dir: str = ""):
    """Generate all JSON data files for the static site."""
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(script_dir), "docs", "data")
    os.makedirs(output_dir, exist_ok=True)

    # Run full multi-sport analysis
    results_by_group = run_full_analysis(api_key)

    if not results_by_group:
        print("ERROR: No results generated")
        sys.exit(1)

    # Build sport groups index and write event files
    sport_groups_index = []

    for group_key, event_reports in results_by_group.items():
        group_cfg = SPORT_GROUPS.get(group_key, {})

        events_index = []
        for report in event_reports:
            # Create URL-safe filename
            slug = report["sport_key"].replace("/", "_")
            filename = f"{slug}.json"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"  Wrote: {filename}")

            # Classify event
            sport_key = report["sport_key"].lower()
            is_major = any(m in sport_key for m in [
                "masters", "pga_championship", "us_open", "open_championship",
                "super_bowl", "championship_winner", "conference_winner",
            ])

            days = report.get("days_to_resolution", 0)
            event_type = "current_week" if days <= 7 else "futures"

            # Count picks
            total_strong = 0
            total_notable = 0
            available_markets = []
            for mk, md in report.get("markets", {}).items():
                if "error" in md:
                    continue
                total_strong += len(md.get("strong_picks", []))
                total_notable += len(md.get("notable_picks", []))
                available_markets.append({
                    "key": mk,
                    "name": MARKET_DISPLAY_NAMES.get(mk, mk),
                })

            events_index.append({
                "event_id": report["event_id"],
                "event_name": report["event_name"],
                "sport_key": report["sport_key"],
                "event_date": report["event_date"],
                "days_to_resolution": days,
                "event_type": event_type,
                "is_major": is_major,
                "data_file": filename,
                "available_markets": available_markets,
                "total_strong_picks": total_strong,
                "total_notable_picks": total_notable,
                "generated_at": report["generated_at"],
            })

        # Sort: current week first, then by date
        events_index.sort(key=lambda x: (
            0 if x["event_type"] == "current_week" else 1,
            x["event_date"]
        ))

        sport_groups_index.append({
            "group_key": group_key,
            "display_name": group_cfg.get("display_name", group_key),
            "icon": group_cfg.get("icon", ""),
            "num_events": len(events_index),
            "total_strong": sum(e["total_strong_picks"] for e in events_index),
            "total_notable": sum(e["total_notable_picks"] for e in events_index),
            "events": events_index,
        })

    # Sort sport groups: golf first, then alphabetically
    group_order = {"golf": 0, "nba": 1, "ncaab": 2, "nfl": 3, "ncaaf": 4}
    sport_groups_index.sort(key=lambda x: group_order.get(x["group_key"], 99))

    # Build top picks across ALL sports for the summary page
    top_picks = []
    for group_key, event_reports in results_by_group.items():
        group_cfg = SPORT_GROUPS.get(group_key, {})
        for report in event_reports:
            for mk, md in report.get("markets", {}).items():
                if isinstance(md, dict) and "error" not in md:
                    for pick in md.get("strong_picks", []) + md.get("notable_picks", []):
                        top_picks.append({
                            "player": pick["player"],
                            "book": pick.get("book_display", pick.get("book", "")),
                            "american_odds": pick["american_odds"],
                            "fair_american": pick["fair_american"],
                            "ev_pct": pick["ev_pct"],
                            "true_prob": pick.get("true_prob", 0),
                            "kelly_pct": pick.get("kelly_pct", 0),
                            "value_tier": pick.get("value_tier", ""),
                            "event_name": report["event_name"],
                            "sport_group": group_key,
                            "sport_icon": group_cfg.get("icon", ""),
                            "sport_name": group_cfg.get("display_name", group_key),
                            "days_to_resolution": report.get("days_to_resolution", 0),
                            "market": MARKET_DISPLAY_NAMES.get(mk, mk),
                        })
    top_picks.sort(key=lambda x: x["ev_pct"], reverse=True)

    # Write main index
    index_data = {
        "site_name": NEWSLETTER_NAME,
        "tagline": NEWSLETTER_TAGLINE,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_free_rate": RISK_FREE_RATE,
        "base_edge_minimum": BASE_EDGE_MINIMUM,
        "top_picks": top_picks[:50],  # Top 50 across all sports
        "sport_groups": sport_groups_index,
    }

    index_path = os.path.join(output_dir, "events.json")
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2, default=str)

    total_events = sum(g["num_events"] for g in sport_groups_index)
    total_strong = sum(g["total_strong"] for g in sport_groups_index)
    print(f"\n  Wrote events index: {len(sport_groups_index)} sports, {total_events} events, {total_strong} strong picks")

    # Timestamp
    ts_path = os.path.join(output_dir, "last_updated.json")
    with open(ts_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "num_sports": len(sport_groups_index),
            "num_events": total_events,
        }, f)

    print(f"\n  Site data generation complete!")
    return sport_groups_index


if __name__ == "__main__":
    use_live = "--live" in sys.argv
    key = ODDS_API_KEY if use_live else ""

    if use_live and not ODDS_API_KEY:
        print("ERROR: Set ODDS_API_KEY environment variable for live mode")
        sys.exit(1)

    generate_site_data(key)
