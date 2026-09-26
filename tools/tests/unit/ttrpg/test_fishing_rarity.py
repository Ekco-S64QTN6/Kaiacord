"""The rarity ladder under catch bonuses."""

def test_better_fishing_gear_widens_every_rare_tier_and_keeps_their_order():
    """Real catches with top gear ran mythic 4.2%, legendary 0.5%: the bonus all landed on mythic."""
    from collections import Counter
    from utils.ttrpg.fishing_engine import rarity_for
    base = Counter(rarity_for(r, 0) for r in range(1, 1001))
    best = Counter(rarity_for(r, 50) for r in range(1, 1001))
    order = ["mythic", "legendary", "epic", "rare", "uncommon"]
    assert all(best[a] <= best[b] for a, b in zip(order, order[1:]))
    assert all(best[c] >= base[c] for c in order) and best["common"] < base["common"]
    assert best["mythic"] <= 3
