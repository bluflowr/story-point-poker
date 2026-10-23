"""The summary shown when the cards are revealed."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

# Cards that mean "I can't estimate" rather than an estimate. They are shown
# in the counts but left out of the stats.
NON_ESTIMATES = {"?", "☕"}


# Fractions people commonly put on cards.
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def _as_number(card):
    if card in FRACTIONS:
        return FRACTIONS[card]
    try:
        return float(card)
    except ValueError:
        return None


def _format_number(value):
    # Round halves up (5.25 -> 5.3), which is what people expect to see.
    rounded = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{rounded}".rstrip("0").rstrip(".")


def summarize(votes, deck):
    """
    votes: the card values played this round (empty votes already removed).
    deck: the room's cards, used to order the counts.
    """
    counted = [vote for vote in votes if vote not in NON_ESTIMATES]
    tally = Counter(votes)

    summary = {
        "total": len(votes),
        "counts": [(card, tally[card]) for card in deck if tally[card]],
        "consensus": counted[0] if len(counted) >= 2 and len(set(counted)) == 1 else None,
        "average": None,
        "low": None,
        "high": None,
        "most_common": [],
    }
    if not counted:
        return summary

    numbers = [_as_number(vote) for vote in counted]
    if all(number is not None for number in numbers):
        summary["average"] = _format_number(sum(numbers) / len(numbers))
        summary["low"] = min(counted, key=_as_number)
        summary["high"] = max(counted, key=_as_number)
    else:
        # Non-numeric decks (e.g. T-shirt sizes): report the most played card(s).
        counted_tally = Counter(counted)
        top = max(counted_tally.values())
        summary["most_common"] = [card for card in deck if counted_tally[card] == top]
    return summary
