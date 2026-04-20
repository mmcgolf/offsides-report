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

    # Binary search for k
    lo, hi = 0.5, 2.0
    for _ in range(200):
        k = (lo + hi) / 2
        total = sum(p ** k for p in implied_probs if p > 0)
        if total > 1.0:
            lo = k
        else:
            hi = k
        if abs(total - 1.0) < tol:
            break

    return [p ** k if p > 0 else 0 for p in implied_probs]


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
    vig_weight: bool = True,
) -> dict[str, float]:
    """
    Calculate consensus (true) probability for each outcome.

    Strategy:
    1. If sharp_books are specified, use ONLY those books (best approach).
    2. Otherwise, weight each book by its sharpness (inverse of overround).
       A book with 32% overround gets ~2x the weight of one with 67%.
    3. Remove vig from the weighted average using the specified method.

    This prevents high-vig books from inflating the consensus probabilities,
    which would make even fair prices at sharp books look like -EV.

    Args:
        outcomes_by_book: {book_name: {outcome: implied_prob}}
        method: vig removal method ("multiplicative", "power", "additive")
        sharp_books: if provided, only use these books for consensus
        vig_weight: if True, weight books by inverse overround (default)

    Returns:
        {outcome: true_probability}
    """
    # Collect all unique outcomes
    all_outcomes = set()
    for book_probs in outcomes_by_book.values():
        all_outcomes.update(book_probs.keys())

    # Filter to sharp books if specified
    books_to_use = outcomes_by_book
    if sharp_books:
        books_to_use = {k: v for k, v in outcomes_by_book.items() if k in sharp_books}
        if not books_to_use:
            books_to_use = outcomes_by_book  # Fallback to all books

    # Calculate weights: inverse of overround (sharper = higher weight)
    book_weights = {}
    if vig_weight and not sharp_books:
        for book, probs in books_to_use.items():
            overround = sum(probs.values())
            # Weight = 1 / overround. A book at 1.32 (32% vig) gets weight ~0.76,
            # while a book at 1.67 (67% vig) gets weight ~0.60
            book_weights[book] = 1.0 / overround if overround > 0 else 0
    else:
        # Equal weight if using sharp books or vig_weight disabled
        for book in books_to_use:
            book_weights[book] = 1.0

    # Weighted average of implied probabilities
    avg_probs = {}
    for outcome in all_outcomes:
        weighted_sum = 0.0
        weight_total = 0.0
        for book, book_probs in books_to_use.items():
            if outcome in book_probs:
                w = book_weights.get(book, 1.0)
                weighted_sum += book_probs[outcome] * w
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
