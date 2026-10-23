"""Card decks: the presets, and the rules for custom decks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Deck:
    label: str
    cards: tuple


FIBONACCI = ["1", "2", "3", "5", "8", "13", "?", "☕"]

PRESETS = {
    "fibonacci": Deck("Fibonacci", tuple(FIBONACCI)),
    "tshirt": Deck("T-shirt sizes", ("XS", "S", "M", "L", "XL", "?", "☕")),
    "powers": Deck("Powers of 2", ("1", "2", "4", "8", "16", "?", "☕")),
}
DEFAULT_KEY = "fibonacci"
CUSTOM_KEY = "custom"

MIN_CARDS = 2
MAX_CARDS = 15
MAX_CARD_LENGTH = 4


class DeckError(ValueError):
    pass


def default_deck():
    # JSONField needs a callable default so rooms don't share one list.
    return list(PRESETS[DEFAULT_KEY].cards)


def parse_custom(text):
    """Turn "1, 2, 4, 8, ?" into a list of cards, or raise DeckError."""
    cards = []
    for card in text.split(","):
        card = card.strip()
        if card and card not in cards:
            cards.append(card)

    too_long = [card for card in cards if len(card) > MAX_CARD_LENGTH]
    if too_long:
        raise DeckError(f"Cards can be at most {MAX_CARD_LENGTH} characters: {', '.join(too_long)}")
    if len(cards) < MIN_CARDS:
        raise DeckError(f"A deck needs at least {MIN_CARDS} different cards, separated by commas.")
    if len(cards) > MAX_CARDS:
        raise DeckError(f"A deck can have at most {MAX_CARDS} cards (you entered {len(cards)}).")
    return cards


def key_for(cards):
    """Which preset a room's deck is, or CUSTOM_KEY."""
    for key, deck in PRESETS.items():
        if tuple(cards) == deck.cards:
            return key
    return CUSTOM_KEY
