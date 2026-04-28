"""
Offsides Report - EV Analysis Engine

Core math:
1. Convert American odds → decimal odds → implied probability
2. Remove vig using "total implied probability" method (shin/power/multiplicative)
3. Calculate true probability for each outcome
4. Compare each book's price to true probability
5. Flag positive EV selections, adjusted for time value of money
"""

import math
from typing import Optional


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return 1 + (american / 100)
    else:
        return 1 + (100 / abs(american))


def decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to American odds."""
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    else:
        return round(-100 / (decimal_odds - 1))


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (includes vig)."""
    return 1.0 / decimal_odds


def implied_prob_to_decimal(prob: float) -> float:
    """Convert probability to fair decimal odds."""
    if prob <= 0:
        return float('inf')
    return 1.0 / prob


# ── Vig Removal Methods ──────────────────────────────────────

def remove_vig_multiplicative(implied_probs: list[float]) -> list[float]:
    """
    Multiplicative method (simplest): scale all probabilities proportionally
    so they sum to 1.0.

    Good for: markets with many outcomes (e.g., tournament winner with 150 golfers)
    """
    total = sum(implied_probs)
    if total == 0:
        return implied_probs
    return [p / total for p in implied_probs]


def remove_vig_power(implied_probs: list[float], tol: float = 1e-8) -> list[float]:
    """
    Power method (Shin-like): find exponent k such that sum(p_i^k) = 1.
    This deviates more vig from favorites and less from longshots,
    which better reflects how books actually set odds.

    More accurate for: futures markets where longshots are overpriced
    """
    if not implied_probs or all(p == 0 for p in implied_probs):
        return implied_probs

    # Check if vig removal is even needed
    total_raw = sum(p for p in implied_probs if p > 0)
    if abs(total_raw - 1.0) < tol:
        return implied_probs

    # Binary search for k — wide range to handle extreme futures markets
    # (e.g., 150-player golf fields with 200%+ overround)
    lo, hi = 0.01, 50.0
    k = 1.0  # default fallback
    for _ in range(500):
        k = (lo + hi) / 2
        total = sum(p ** k for p in implied_probs if p > 0)
        if total > 1.0:
            lo = k
        else:
            hi = k
        if abs(total - 1.0) < tol:
            break

    result = [p ** k if p > 0 else 0 for p in implied_probs]

    # Sanity check: if power method produced degenerate results, fall back
    # to multiplicative (simpler but always works)
    if any(r > 0.99 for r in result) and len(result) > 2:
        return remove_vig_multiplicative(implied_probs)

    return result


def remove_vig_additive(implied_probs: list[float]) -> list[float]:
    """
    Additive method: subtract equal amount from each probability.

    Rarely best choice, but included for completeness.
    """
    total = sum(implied_probs)
    n = len(implied_probs)
    excess = (total - 1.0) / n
    adjusted = [max(p - excess, 0.001) for p in implied_probs]
    # Renormalize in case of clipping
    adj_total = sum(adjusted)
    return [p / adj_total for p in adjusted]


# ── Market-Level Vig Calculation ──────────────────────────────

def calculate_market_vig(implied_probs: list[float]) -> float:
    """
    Calculate the total vig (overround) for a market.
    Returns as a percentage (e.g., 0.15 = 15% overround).
    """
    return sum(implied_probs) - 1.0


def calculate_hold_percentage(implied_probs: list[float]) -> float:
    """
    Calculate the book's theoretical hold percentage.
    """
    total = sum(implied_probs)
    if total == 0:
        return 0
    return (total - 1.0) / total


# ── Consensus / True Probability ──────────────────────────────

def calculate_consensus_probabilities(
    outcomes_by_book: dict[str, dict[str, float]],
    method: str = "power",
    sharp_books: Optional[list[str]] = None,
    sharp_weight: float = 3.0,
    vig_weight: bool = True,
    min_books: int = 2,
    nc_books: Optional[list[str]] = None,
) -> dict[str, float]:
    """
    Calculate consensus (true) probability for each outcome.

    Strategy:
    1. Use ALL books, but give sharp books extra weight (sharp_weight multiplier).
       This blends sharp and NC views so the consensus reflects the whole market.
       Using sharp-only caused false +EV for every longshot because NC books
       have higher vig on longshots than sharp books.
    2. Weight each book by inverse overround (sharper = higher weight).
    3. Apply sharp_weight multiplier on top for designated sharp books.
    4. Remove vig from the weighted average using the specified method.

    Args:
        outcomes_by_book: {book_name: {outcome: implied_prob}}
        method: vig removal method ("multiplicative", "power", "additive")
        sharp_books: books to give extra weight (not exclusive filter)
        sharp_weight: multiplier for sharp book weights (default 3.0)
        vig_weight: if True, weight books by inverse overround (default)
        min_books: minimum number of books that must list an outcome
                   for it to be included in consensus (prevents distortion
                   from single-book outliers like Tiger Woods at 1 book)
        nc_books: list of NC-legal book keys. If provided, outcomes must
                  appear at 1+ NC book to be included (no point pricing
                  outcomes you can't bet on).

    Returns:
        {outcome: true_probability}
    """
    nc_set = set(nc_books) if nc_books else set()
    sharp_set = set(sharp_books) if sharp_books else set()

    # When sharp books provided, use ONLY them for probability calculation
    # (they're the most accurate reference). Otherwise use all books.
    if sharp_set:
        prob_books = {k: v for k, v in outcomes_by_book.items() if k in sharp_set}
        if not prob_books:
            prob_books = outcomes_by_book  # Fallback
    else:
        prob_books = outcomes_by_book

    # Count NC book coverage (using ALL books, not just prob_books)
    outcome_nc_count = {}
    for book_key, book_probs in outcomes_by_book.items():
        if book_key in nc_set:
            for outcome in book_probs:
                outcome_nc_count[outcome] = outcome_nc_count.get(outcome, 0) + 1

    # Count how many prob_books list each outcome
    outcome_book_count = {}
    for book_probs in prob_books.values():
        for outcome in book_probs:
            outcome_book_count[outcome] = outcome_book_count.get(outcome, 0) + 1

    # Only include outcomes that:
    # 1. Appear at min_books or more probability books
    # 2. Appear at 1+ NC book — no point pricing outcomes you can't bet on,
    #    and garbage data (Tiger at +100) distorts vig removal for everyone
    total_books = len(prob_books)
    effective_min = min(min_books, max(1, total_books))
    qualified_outcomes = set()
    for outcome, count in outcome_book_count.items():
        if count < effective_min:
            continue
        if nc_set and outcome_nc_count.get(outcome, 0) == 0:
            continue
        qualified_outcomes.add(outcome)

    # Calculate weights for prob_books
    book_weights = {}
    for book, probs in prob_books.items():
        if vig_weight:
            overround = sum(probs.values())
            w = 1.0 / overround if overround > 0 else 0
        else:
            w = 1.0
        book_weights[book] = w

    # Weighted average of implied probabilities (only qualified outcomes)
    avg_probs = {}
    for outcome in qualified_outcomes:
        weighted_sum = 0.0
        weight_total = 0.0
        for book, book_probs in prob_books.items():
            if outcome in book_probs:
                imp = book_probs[outcome]
                w = book_weights.get(book, 1.0)
                weighted_sum += imp * w
                weight_total += w
        if weight_total > 0:
            avg_probs[outcome] = weighted_sum / weight_total
        else:
            avg_probs[outcome] = 0.0

    # Remove vig
    outcomes_list = sorted(avg_probs.keys())
    implied_list = [avg_probs[o] for o in outcomes_list]

    vig_removers = {
        "multiplicative": remove_vig_multiplicative,
        "power": remove_vig_power,
        "additive": remove_vig_additive,
    }

    remover = vig_removers.get(method, remove_vig_power)
    true_probs_list = remover(implied_list)

    return dict(zip(outcomes_list, true_probs_list))


# ── EV Calculation ────────────────────────────────────────────

def calculate_ev(
    offered_decimal_odds: float,
    true_probability: float,
) -> float:
    """
    Calculate expected value of a bet.

    EV = (true_prob * (decimal_odds - 1)) - (1 - true_prob)

    Positive = profitable in the long run.
    Returns as a fraction (0.05 = 5% edge).
    """
    return (true_probability * (offered_decimal_odds - 1)) - (1 - true_probability)


def calculate_ev_percentage(
    offered_decimal_odds: float,
    true_probability: float,
) -> float:
    """
    Calculate EV as a percentage of the stake.
    """
    return calculate_ev(offered_decimal_odds, true_probability) * 100


# ── Time-Adjusted EV Threshold ────────────────────────────────

def minimum_edge_threshold(
    days_to_resolution: int,
    risk_free_rate: float = 0.045,
    base_edge: float = 0.02,
) -> float:
    """
    Calculate the minimum edge required given the time value of money.

    A bet that locks up capital for N days should offer more edge than
    the risk-free return over that period, plus a base minimum.

    For a 4-day tournament winner: ~2.05% minimum
    For a 9-month Super Bowl future: ~5.4% minimum

    Returns as a fraction (e.g., 0.05 = 5%).
    """
    time_cost = (days_to_resolution / 365) * risk_free_rate
    return base_edge + time_cost


def classify_value(
    ev_pct: float,
    days_to_resolution: int,
    risk_free_rate: float = 0.045,
    base_edge: float = 0.02,
) -> Optional[str]:
    """
    Classify a bet's value tier based on time-adjusted thresholds.

    Returns: "STRONG VALUE", "Notable Value", or None
    """
    min_edge = minimum_edge_threshold(days_to_resolution, risk_free_rate, base_edge)
    ev_fraction = ev_pct / 100

    if ev_fraction >= min_edge * 2:
        return "STRONG VALUE"
    elif ev_fraction >= min_edge:
        return "Notable Value"
    return None


# ── Kelly Criterion ───────────────────────────────────────────

def kelly_fraction(
    offered_decimal_odds: float,
    true_probability: float,
    kelly_multiplier: float = 0.25,  # Quarter-Kelly is standard for sports
) -> float:
    """
    Calculate the Kelly criterion bet size as a fraction of bankroll.

    Full Kelly is too aggressive for most bettors; quarter-Kelly is standard.

    Returns: fraction of bankroll to wager (e.g., 0.02 = 2%)
    """
    b = offered_decimal_odds - 1  # Net payout per unit
    p = true_probability
    q = 1 - p

    if b <= 0 or p <= 0:
        return 0.0

    full_kelly = (b * p - q) / b
    return max(0, full_kelly * kelly_multiplier)


# ── Outlier Detection ─────────────────────────────────────────

def detect_odds_outliers(
    outcome_odds_by_book: dict[str, float],
    threshold_pct: float = 20.0,
) -> list[dict]:
    """
    Find books whose odds on a specific outcome deviate significantly
    from the market consensus.

    This is the core "where do the books disagree" detection.

    Args:
        outcome_odds_by_book: {book_name: decimal_odds} for ONE outcome
        threshold_pct: minimum % deviation from median to flag

    Returns:
        List of {book, odds, deviation_pct, direction} for outlier books
    """
    if len(outcome_odds_by_book) < 3:
        return []

    odds_values = sorted(outcome_odds_by_book.values())
    n = len(odds_values)
    median_odds = odds_values[n // 2]

    if median_odds == 0:
        return []

    outliers = []
    for book, odds in outcome_odds_by_book.items():
        deviation = ((odds - median_odds) / median_odds) * 100
        if abs(deviation) >= threshold_pct:
            outliers.append({
                "book": book,
                "decimal_odds": odds,
                "american_odds": decimal_to_american(odds),
                "median_odds": median_odds,
                "median_american": decimal_to_american(median_odds),
                "deviation_pct": round(deviation, 1),
                "direction": "higher" if deviation > 0 else "lower",
            })

    return sorted(outliers, key=lambda x: abs(x["deviation_pct"]), reverse=True)
