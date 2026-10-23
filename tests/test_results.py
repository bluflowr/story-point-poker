from rooms.decks import FIBONACCI
from rooms.results import summarize

TSHIRT = ["XS", "S", "M", "L", "XL", "?", "☕"]


def test_numeric_votes_give_average_low_and_high():
    summary = summarize(["3", "5", "8", "5"], FIBONACCI)
    assert summary["average"] == "5.3"
    assert summary["low"] == "3"
    assert summary["high"] == "8"
    assert summary["consensus"] is None
    assert summary["counts"] == [("3", 1), ("5", 2), ("8", 1)]


def test_whole_number_average_has_no_decimal():
    assert summarize(["3", "5"], FIBONACCI)["average"] == "4"


def test_question_mark_and_coffee_are_counted_but_not_averaged():
    summary = summarize(["5", "8", "?", "☕"], FIBONACCI)
    assert summary["average"] == "6.5"
    assert summary["total"] == 4
    assert ("?", 1) in summary["counts"]
    assert ("☕", 1) in summary["counts"]


def test_consensus_needs_two_matching_estimates():
    assert summarize(["5", "5", "?"], FIBONACCI)["consensus"] == "5"
    assert summarize(["5"], FIBONACCI)["consensus"] is None
    assert summarize(["5", "8"], FIBONACCI)["consensus"] is None


def test_only_non_estimates_gives_no_stats():
    summary = summarize(["?", "☕"], FIBONACCI)
    assert summary["average"] is None
    assert summary["most_common"] == []


def test_no_votes():
    summary = summarize([], FIBONACCI)
    assert summary["total"] == 0
    assert summary["counts"] == []


def test_non_numeric_deck_reports_most_common_in_deck_order():
    summary = summarize(["M", "L", "M", "L", "S"], TSHIRT)
    assert summary["average"] is None
    assert summary["most_common"] == ["M", "L"]
