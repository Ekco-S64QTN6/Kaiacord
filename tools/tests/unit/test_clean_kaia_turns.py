"""Historical cleanup must compare each turn with cleaned prior turns."""
from tools.maintenance import clean_kaia_turns as cleaner


def test_clean_log_carries_forward_the_cleaned_turn(monkeypatch):
    seen_previous = []

    def fake_clean(text, previous):
        seen_previous.append(list(previous))
        return f"cleaned {text}"

    monkeypatch.setattr(cleaner, "clean", fake_clean)
    raw = (
        "[2026-10-01 12:00:00] Kaia: first\n"
        "[2026-10-01 12:00:01] Kaia: second\n"
    )

    rewritten, changes = cleaner.clean_log(raw, [])

    assert seen_previous == [[], ["cleaned first"]]
    assert len(changes) == 2
    assert "Kaia: cleaned first" in rewritten
    assert "Kaia: cleaned second" in rewritten


def test_channel_memory_cleaner_also_carries_forward_cleaned_turns():
    import inspect

    source = inspect.getsource(cleaner.main)
    assert source.count("previous.append(new)") == 1
    assert "previous.append(text)" not in source
