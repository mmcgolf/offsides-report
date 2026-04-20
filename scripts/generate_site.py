#!/usr/bin/env python3
"""
Offsides Report - Static Site Generator

Runs the full analysis pipeline and outputs JSON data files
for the static site to consume. Designed to run in GitHub Actions.

Usage:
    python generate_site.py              # Uses demo data
    python generate_site.py --live       # Uses live API (requires ODDS_API_KEY env var)
"""

import json
import os
import sys
from datetime import datetime

# Ensure we can import our modules
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from analysis import run_full_analysis
from config import (
    ODDS_API_KEY,
    NEWSLETTER_NAME,
    NEWSLETTER_TAGLINE,
    RISK_FREE_RATE,
    BASE_EDGE_MINIMUM,
    BOOK_DISPLAY_NAMES,
    MARKET_DISPLAY_NAMES,
)


def generate_site_data(api_key: str = "", output_dir: str = ""):
    """Generate all JSON data files for the static site."""
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(script_dir), "docs", "data")
    os.makedirs(output_dir, exist_ok=True)

    # Run full analysis
    event_reports = run_full_analysis(api_key)

    if not event_reports:
        print("ERROR: No event reports generated")
        sys.exit(1)

    # Write individual event files
    events_index = []
    for report in event_reports:
        # Create a URL-safe filename from the sport key
        slug = report["sport_key"].replace("/", "_")
        filename = f"{slug}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  Wrote: {filename}")

        # Classify event type
        sport_key = report["sport_key"].lower()
        is_major = any(m in sport_key for m in [
            "masters", "pga_championship", "us_open", "open_championship"
        ])

        # Determine if this is current week or futures
        days = report.get("days_to_resolution", 0)
        event_type = "current_week" if days <= 7 else "futures"

        # Count value picks across all markets
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

    # Write events index
    index_data = {
        "site_name": NEWSLETTER_NAME,
        "tagline": NEWSLETTER_TAGLINE,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_free_rate": RISK_FREE_RATE,
        "base_edge_minimum": BASE_EDGE_MINIMUM,
        "events": events_index,
    }

    index_path = os.path.join(output_dir, "events.json")
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2, default=str)
    print(f"\n  Wrote events index: events.json ({len(events_index)} events)")

    # Write a last-updated timestamp
    ts_path = os.path.join(output_dir, "last_updated.json")
    with open(ts_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "num_events": len(events_index),
        }, f)

    print(f"\n  Site data generation complete!")
    print(f"  Output directory: {output_dir}")
    return events_index


if __name__ == "__main__":
    use_live = "--live" in sys.argv
    key = ODDS_API_KEY if use_live else ""

    if use_live and not ODDS_API_KEY:
        print("ERROR: Set ODDS_API_KEY environment variable for live mode")
        print("  export ODDS_API_KEY=your_key_here")
        print("  Or add it to GitHub Secrets")
        sys.exit(1)

    generate_site_data(key)
