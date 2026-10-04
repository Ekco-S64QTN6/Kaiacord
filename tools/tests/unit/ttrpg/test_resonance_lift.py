"""The Resonance Lift: a stop at every fifth floor of the Ironvein Deep the player has reached."""
import asyncio


def test_the_lift_stops_at_every_fifth_floor_reached():
    """Standing on floor 20 means guardians 1–19 are beaten; the lift offered
    5, 10 and 15, holding each stop back until that floor's own guardian fell."""
    from utils.ttrpg.rpg_views import SpineLiftView
    from utils.ttrpg.spine_dungeon import deepest_reached, MAX_FLOOR
    assert deepest_reached({}) == 1 and deepest_reached({"spine_defeated_guards": [1, 2, 3, 4]}) == 5
    assert deepest_reached({"spine_defeated_guards": list(range(1, MAX_FLOOR + 1))}) == MAX_FLOOR
    sheet = {"spine_defeated_guards": list(range(1, 20))}

    async def build():
        view = SpineLiftView(None, "1", "Ekco", True, sheet, deepest_reached(sheet))
        return [o.value for o in view.children[0].options]
    assert asyncio.run(build()) == ["1", "5", "10", "15", "20"]
