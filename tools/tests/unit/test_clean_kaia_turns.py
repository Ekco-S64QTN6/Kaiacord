"""Historical cleanup must compare each turn with cleaned prior turns, and an
opening with what she actually said."""
from tools.maintenance import clean_kaia_turns as cleaner


def test_clean_log_carries_forward_the_cleaned_turn(monkeypatch):
    seen_previous, seen_said = [], []

    def fake_clean(text, previous, said=None):
        seen_previous.append(list(previous))
        seen_said.append(list(said or []))
        return f"cleaned {text}"

    monkeypatch.setattr(cleaner, "clean", fake_clean)
    raw = (
        "[2026-10-01 12:00:00] Kaia: first\n"
        "[2026-10-01 12:00:01] Kaia: second\n"
    )

    rewritten, changes = cleaner.clean_log(raw, [])

    assert seen_previous == [[], ["cleaned first"]]
    assert seen_said == [[], ["first"]]
    assert len(changes) == 2
    assert "Kaia: cleaned first" in rewritten
    assert "Kaia: cleaned second" in rewritten


def test_channel_memory_cleaner_also_carries_forward_cleaned_turns():
    import inspect

    source = inspect.getsource(cleaner.main)
    assert source.count("previous.append(new)") == 1
    assert "previous.append(text)" not in source


def test_a_repeated_opening_is_counted_against_what_she_said():
    """Counted against the cleaned turns, a dropped opening stopped counting and
    came back every few turns."""
    rest = ["the river was high again and the bridge stayed closed until noon.",
            "my neighbour finally fixed the gate that has squeaked since spring.",
            "pixel spent the whole afternoon chasing a moth around the lamp.",
            "the bakery on the corner ran out of rye bread before ten o'clock.",
            "someone left a bicycle chained to the railing outside my window.",
            "the radiator clanks every time the heating comes on at night.",
            "a parcel arrived for the flat upstairs and nobody has claimed it."]
    lead = ["rain", "habits", "kettles", "mornings", "neighbours", "radiators", "parcels"]
    raw = "".join(f"[2026-11-08 07:2{i}:00] Kaia: it’s funny how {w} keep surprising us, isn’t it? {r}\n\n"
                  for i, (w, r) in enumerate(zip(lead, rest)))
    rewritten, changes = cleaner.clean_log(raw, [], [])
    assert rewritten.count("it’s funny how") == 2
    assert all(r in rewritten for r in rest)
