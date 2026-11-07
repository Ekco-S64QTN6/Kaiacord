"""character_manager.load() and a character + housing commit take the housing
transaction lock and the sheet lock in the same order (CLAUDE.md §4)."""
import asyncio, time, json
from datetime import date
from utils.ttrpg import character_manager, housing, housing_transactions

def test_a_daily_housing_reset_and_a_housing_commit_for_one_player_do_not_deadlock(tmp_path, monkeypatch):
    chars = tmp_path / "chars"; homes = tmp_path / "homes"; chars.mkdir(); homes.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(chars))
    monkeypatch.setattr(housing, "HOUSING_DIR", str(homes))
    monkeypatch.setattr(housing_transactions, "_journal_dir", lambda: str(tmp_path / "journal"))
    today = date.today().isoformat()
    sheet = {"user_id": "42", "character_name": "T", "hunts_reset_date": today, "inventory": [], "gil": 0,
             "hp": {"current": 10, "max": 10}, "level": 1, "xp": 0, "class": "Warrior"}
    (chars / "42.json").write_text(json.dumps(sheet))
    home = housing.default_housing_sheet("42", "T"); home["last_farm_reset"] = "2000-01-01"
    housing.save_housing(home)

    real_load_sync = character_manager._load_sync
    def slow_load_sync(uid):
        time.sleep(0.3)          # X holds the per-user sheet lock while reading
        return real_load_sync(uid)
    monkeypatch.setattr(character_manager, "_load_sync", slow_load_sync)

    async def scenario():
        x = asyncio.create_task(character_manager.load("42"))          # path X
        await asyncio.sleep(0.1)                                        # X now holds the sheet lock
        y_home = housing.default_housing_sheet("42", "T")
        y = asyncio.create_task(housing_transactions.commit_character_resource(
            dict(sheet), y_home, resource_kind="housing", action="buy_furniture"))  # path Y
        done, pending = await asyncio.wait({x, y}, timeout=3)
        for t in pending: t.cancel()
        return len(pending)
    stuck = asyncio.run(scenario())
    assert stuck == 0, f"{stuck} task(s) deadlocked"
