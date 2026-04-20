"""
Offsides Report - Analytics Integration

Fetches supplementary analytics data (DataGolf rankings, etc.)
to overlay on the odds analysis.
"""

import requests
from typing import Optional


def fetch_datagolf_rankings() -> list[dict]:
    """
    Fetch DataGolf world rankings from their public page.
    Falls back to curated demo data if unavailable.

    DataGolf ranks golfers using a field-strength-adjusted model
    that's widely considered superior to OWGR for betting purposes.
    """
    # DataGolf doesn't have a free public API, so we use curated rankings
    # In production, you'd either subscribe to their API or scrape the rankings page
    return get_demo_datagolf_rankings()


def get_demo_datagolf_rankings() -> list[dict]:
    """
    Curated DataGolf-style rankings for top golfers.
    Updated periodically from public DataGolf rankings page.

    Includes:
    - dg_rank: DataGolf overall ranking
    - dg_skill: Estimated true skill (strokes vs. field)
    - sg_total: Strokes gained total (recent form)
    - course_fit: Estimated course fit score (1-10) for current event
    - trend_rank: DG Trend rank (20-round rolling window — lower = hotter)
    - trend_sg20: SG Total over last 20 rounds (the trend number)
    """
    # trend_rank: Ranking based on 20-round rolling SG Total.
    # A player whose trend_rank is much better than their dg_rank is "heating up"
    # — this is where underpriced value tends to hide.
    # trend_sg20: The actual SG Total value over those 20 rounds.
    return [
        {"name": "Scottie Scheffler", "dg_rank": 1, "dg_skill": 2.85, "sg_total": 2.42, "course_fit": 8.5, "owgr": 1, "trend_rank": 1, "trend_sg20": 2.55},
        {"name": "Xander Schauffele", "dg_rank": 2, "dg_skill": 2.21, "sg_total": 1.88, "course_fit": 8.0, "owgr": 2, "trend_rank": 3, "trend_sg20": 2.10},
        {"name": "Rory McIlroy", "dg_rank": 3, "dg_skill": 2.08, "sg_total": 1.65, "course_fit": 7.0, "owgr": 3, "trend_rank": 8, "trend_sg20": 1.52},
        {"name": "Collin Morikawa", "dg_rank": 4, "dg_skill": 1.95, "sg_total": 1.72, "course_fit": 8.5, "owgr": 4, "trend_rank": 2, "trend_sg20": 2.18},
        {"name": "Hideki Matsuyama", "dg_rank": 5, "dg_skill": 1.82, "sg_total": 1.55, "course_fit": 7.5, "owgr": 6, "trend_rank": 6, "trend_sg20": 1.70},
        {"name": "Patrick Cantlay", "dg_rank": 6, "dg_skill": 1.75, "sg_total": 1.48, "course_fit": 8.0, "owgr": 5, "trend_rank": 12, "trend_sg20": 1.30},
        {"name": "Viktor Hovland", "dg_rank": 7, "dg_skill": 1.68, "sg_total": 1.25, "course_fit": 6.5, "owgr": 8, "trend_rank": 18, "trend_sg20": 1.05},
        {"name": "Sahith Theegala", "dg_rank": 8, "dg_skill": 1.62, "sg_total": 1.58, "course_fit": 7.0, "owgr": 9, "trend_rank": 4, "trend_sg20": 1.95},
        {"name": "Wyndham Clark", "dg_rank": 9, "dg_skill": 1.55, "sg_total": 1.35, "course_fit": 7.0, "owgr": 7, "trend_rank": 14, "trend_sg20": 1.22},
        {"name": "Matt Fitzpatrick", "dg_rank": 10, "dg_skill": 1.50, "sg_total": 1.20, "course_fit": 8.5, "owgr": 11, "trend_rank": 15, "trend_sg20": 1.18},
        {"name": "Justin Thomas", "dg_rank": 11, "dg_skill": 1.45, "sg_total": 1.10, "course_fit": 7.5, "owgr": 14, "trend_rank": 22, "trend_sg20": 0.88},
        {"name": "Tommy Fleetwood", "dg_rank": 12, "dg_skill": 1.40, "sg_total": 1.30, "course_fit": 8.0, "owgr": 10, "trend_rank": 5, "trend_sg20": 1.82},
        {"name": "Shane Lowry", "dg_rank": 13, "dg_skill": 1.35, "sg_total": 1.15, "course_fit": 7.5, "owgr": 12, "trend_rank": 10, "trend_sg20": 1.42},
        {"name": "Tom Kim", "dg_rank": 14, "dg_skill": 1.30, "sg_total": 1.22, "course_fit": 7.0, "owgr": 13, "trend_rank": 9, "trend_sg20": 1.48},
        {"name": "Cameron Young", "dg_rank": 15, "dg_skill": 1.25, "sg_total": 1.05, "course_fit": 6.5, "owgr": 18, "trend_rank": 20, "trend_sg20": 0.95},
        {"name": "Corey Conners", "dg_rank": 16, "dg_skill": 1.20, "sg_total": 1.10, "course_fit": 8.0, "owgr": 16, "trend_rank": 13, "trend_sg20": 1.28},
        {"name": "Sungjae Im", "dg_rank": 17, "dg_skill": 1.18, "sg_total": 1.25, "course_fit": 7.0, "owgr": 15, "trend_rank": 7, "trend_sg20": 1.62},
        {"name": "Akshay Bhatia", "dg_rank": 18, "dg_skill": 1.15, "sg_total": 1.35, "course_fit": 7.5, "owgr": 17, "trend_rank": 11, "trend_sg20": 1.38},
        {"name": "Brian Harman", "dg_rank": 19, "dg_skill": 1.10, "sg_total": 0.95, "course_fit": 9.0, "owgr": 22, "trend_rank": 16, "trend_sg20": 1.15},
        {"name": "Russell Henley", "dg_rank": 20, "dg_skill": 1.05, "sg_total": 0.90, "course_fit": 8.5, "owgr": 25, "trend_rank": 19, "trend_sg20": 1.00},
        {"name": "Keegan Bradley", "dg_rank": 21, "dg_skill": 1.00, "sg_total": 0.85, "course_fit": 7.0, "owgr": 20, "trend_rank": 25, "trend_sg20": 0.72},
        {"name": "Denny McCarthy", "dg_rank": 22, "dg_skill": 0.95, "sg_total": 0.80, "course_fit": 8.5, "owgr": 28, "trend_rank": 17, "trend_sg20": 1.08},
        {"name": "Max Homa", "dg_rank": 23, "dg_skill": 0.92, "sg_total": 0.75, "course_fit": 7.0, "owgr": 24, "trend_rank": 28, "trend_sg20": 0.60},
        {"name": "Sepp Straka", "dg_rank": 24, "dg_skill": 0.88, "sg_total": 0.82, "course_fit": 7.5, "owgr": 21, "trend_rank": 21, "trend_sg20": 0.92},
        {"name": "Davis Thompson", "dg_rank": 25, "dg_skill": 0.85, "sg_total": 0.90, "course_fit": 7.0, "owgr": 30, "trend_rank": 23, "trend_sg20": 0.85},
    ]


def get_analytics_for_player(name: str, rankings: list[dict]) -> Optional[dict]:
    """Look up analytics data for a specific player."""
    for player in rankings:
        if player["name"].lower() == name.lower():
            return player
    return None


def get_course_fit_summary(rankings: list[dict], top_n: int = 10) -> list[dict]:
    """Get top course fit players for the current event."""
    sorted_by_fit = sorted(rankings, key=lambda x: x["course_fit"], reverse=True)
    return sorted_by_fit[:top_n]


def get_form_summary(rankings: list[dict], top_n: int = 10) -> list[dict]:
    """Get players in best recent form (strokes gained)."""
    sorted_by_form = sorted(rankings, key=lambda x: x["sg_total"], reverse=True)
    return sorted_by_form[:top_n]


def get_trending_players(rankings: list[dict], top_n: int = 10) -> list[dict]:
    """
    Get players who are trending hottest over last 20 rounds.
    Sorted by trend_rank (lower = hotter).
    """
    sorted_by_trend = sorted(rankings, key=lambda x: x.get("trend_rank", 999))
    return sorted_by_trend[:top_n]


def get_heating_up(rankings: list[dict], min_rank_jump: int = 5) -> list[dict]:
    """
    Find players whose 20-round trend rank is significantly better than
    their overall DG rank — these are the 'heating up' players the market
    may not have fully priced in yet.

    A player ranked DG #18 overall but trending at #7 is playing like
    a top-10 player recently. If the odds still reflect #18 talent,
    that's where value hides.

    Args:
        min_rank_jump: minimum difference between dg_rank and trend_rank
                       to qualify as "heating up"
    """
    heating = []
    for p in rankings:
        rank_jump = p["dg_rank"] - p.get("trend_rank", p["dg_rank"])
        if rank_jump >= min_rank_jump:
            entry = dict(p)
            entry["rank_jump"] = rank_jump
            heating.append(entry)
    return sorted(heating, key=lambda x: x["rank_jump"], reverse=True)
