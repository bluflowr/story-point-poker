"""Card decks. The deck picker and other presets arrive in milestone 3b."""

FIBONACCI = ["1", "2", "3", "5", "8", "13", "?", "☕"]

DEFAULT_DECK = FIBONACCI


def default_deck():
    # JSONField needs a callable default so rooms don't share one list.
    return list(DEFAULT_DECK)
