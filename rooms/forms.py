from django import forms
from django.utils.html import format_html

from . import decks


class JoinForm(forms.Form):
    display_name = forms.CharField(
        label="Your name",
        max_length=30,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "nickname"}),
    )
    observer = forms.BooleanField(
        label="Join as an observer (watch without voting)",
        required=False,
    )


class RoomOptionsForm(forms.Form):
    control = forms.ChoiceField(
        label="Who controls the round?",
        choices=[
            ("anyone", "Anyone can reveal and start the next round"),
            ("facilitator", "Only the facilitator (you, to start with)"),
        ],
        initial="anyone",
        required=False,  # missing means "anyone"
        widget=forms.RadioSelect,
    )


def _deck_choice(label, cards):
    return format_html('{} <span class="muted small">{}</span>', label, " ".join(cards))


DECK_CHOICES = [(key, _deck_choice(deck.label, deck.cards)) for key, deck in decks.PRESETS.items()] + [
    (decks.CUSTOM_KEY, "Custom")
]


class DeckForm(forms.Form):
    """
    Picks a deck. Used on the home page when creating a room, and inside the
    room (sent over the WebSocket) when switching decks. After validation,
    cleaned_data["cards"] holds the list of cards.
    """

    deck = forms.ChoiceField(choices=DECK_CHOICES, initial=decks.DEFAULT_KEY, widget=forms.RadioSelect)
    custom = forms.CharField(
        label="Your cards",
        required=False,
        max_length=200,
        help_text=f"Separate cards with commas, up to {decks.MAX_CARDS} cards of {decks.MAX_CARD_LENGTH} characters.",
        widget=forms.TextInput(attrs={"placeholder": "e.g. 1, 2, 4, 8, ?, ☕"}),
    )

    @classmethod
    def for_room(cls, room):
        key = decks.key_for(room.deck)
        custom = ", ".join(room.deck) if key == decks.CUSTOM_KEY else ""
        return cls(initial={"deck": key, "custom": custom})

    def clean(self):
        cleaned = super().clean()
        key = cleaned.get("deck")
        if key == decks.CUSTOM_KEY:
            try:
                cleaned["cards"] = decks.parse_custom(cleaned.get("custom", ""))
            except decks.DeckError as error:
                self.add_error("custom", str(error))
        elif key:
            cleaned["cards"] = list(decks.PRESETS[key].cards)
        return cleaned
