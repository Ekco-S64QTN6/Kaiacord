"""
Item drops for monster kills based on their difficulty tier.
Keys match equipment_registry.py so items can be used/sold/equipped.
Gear drops (head, boots, accessories) added at low probability per tier.
Expanded with EQ/FF1-5 drops.
"""
import secrets
from typing import Optional

def get_loot(tier: str) -> Optional[str]:
    """Returns an item key or None."""
    tables = {
        "trivial": [
            ("none", 30), ("healing_herb", 18), ("bandage", 10), ("honey_sap", 20),
            ("worn_cap", 4), ("worn_boots", 4), ("bronze_helm", 3), ("bronze_sabatons", 3),
            ("antidote", 4), ("eye_drops", 4),
            ("gold_needle", 2), ("soft", 2), ("maidens_kiss", 2),
            ("mognet_letter", 4),
            ("rusty_dagger", 5), ("wooden_staff", 5), ("wooden_club", 5),
            ("shortbow", 4), ("hand_axe", 4), ("travelers_cloak", 5), ("torch", 6),
            # Rare Tier 2 injections
            ("iron_sword", 2), ("spear", 2), ("leather_armor", 2), ("tonic", 2),
        ],
        "easy": [
            ("none", 20), ("healing_herb", 12), ("bandage", 10), ("tonic", 7), ("hi_potion", 6),
            ("blood_thistle", 14), ("silver_moss", 10), ("honey_sap", 10),
            ("scouts_hood", 5), ("trackers_boots", 5), ("copper_ring", 7),
            ("bronze_armor", 5), ("bronze_helm", 4), ("bronze_sabatons", 4),
            ("horned_helmet", 3), ("sages_hat", 3), ("striding_boots", 3),
            ("antidote", 3), ("lucky_charm", 3),
            ("iron_staff", 4), ("iron_sword", 4), ("spear", 4), ("crossbow", 4),
            ("battle_axe", 4), ("mages_robe", 4), ("leather_armor", 5),
            ("iron_helm", 4), ("mages_cap", 4), ("heavy_boots", 4), ("soft_slippers", 4),
            ("warriors_bracer", 4), ("scouts_bracer", 4), ("scholars_bracelet", 4),
            # Rare Tier 3-4 injections
            ("mithral_shirt", 2), ("iron_ring", 2), ("flametongue", 1), ("winged_boots", 1),
        ],
        "medium": [
            ("none", 10), ("tonic", 14), ("hi_potion", 10), ("healing_herb", 8), ("bandage", 10),
            ("silver_moss", 12), ("dire_root", 10), ("blood_thistle", 10),
            ("leather_coif", 6), ("shadow_treads", 5), ("iron_ring", 4), ("oak_bracelet", 4),
            ("flame_helm", 4), ("flame_greaves", 4), ("serpentine_bracer", 3),
            ("flame_sword", 3), ("ice_brand", 3),
            ("flametongue", 2), ("frostbrand", 2), ("mithral_shirt", 3),
            ("executioner_hood", 3), ("winged_boots", 2), ("ring_protection", 3),
            ("tonberry_knife", 2),
            ("longsword", 4), ("steel_blade", 4), ("silken_robe", 4),
            ("studded_leather", 4), ("chainmail", 4), ("black_garb", 3), ("fur_cloak", 3),
            ("steel_visor", 3), ("silken_cowl", 3), ("iron_shod_boots", 3),
            ("foresters_boots", 3), ("ley_walkers", 3), ("crystal_bracelet", 3), ("periapt_poison", 3),
            # Rare Tier 4-5 injections
            ("aeridor_shard", 2), ("diamond_armor", 1), ("masamune", 1),
        ],
        "hard": [
            ("none", 6), ("tonic", 10), ("elixir", 6), ("hi_potion", 8),
            ("aeridor_shard", 14), ("dire_root", 12), ("silver_moss", 8),
            ("siege_helm", 5), ("whisperwood_boots", 5), ("silver_ring", 6),
            ("aeridor_bangle", 6), ("gold_ring", 5),
            ("flame_mail", 4), ("ice_armor", 4), ("defender", 3),
            ("diamond_helm", 3), ("diamond_boots", 3),
            ("sun_blade", 2), ("disruption_mace", 2), ("boots_speed", 2),
            ("circlet_persuasion", 3), ("bracers_defense", 2), ("amulet_health", 2),
            ("phoenix_down", 2), ("panacea", 2),
            ("resonance_staff", 3), ("shining_staff", 3), ("yoichi_bow", 3),
            ("ghoulbane", 3), ("ykesha_sword", 3), ("arcane_vestment", 3),
            ("half_plate", 3), ("arcane_circlet", 3), ("gold_hairpin", 3),
            ("ribbon", 3), ("wardens_greaves", 3), ("tricklebrook_charm", 3), ("ether", 5),
        ],
        "deadly": [
            ("tonic", 6), ("elixir", 10), ("phoenix_down", 6),
            ("aeridor_shard", 16), ("dire_root", 8), ("gilded_mushroom", 10),
            ("aeridorian_helm", 5), ("shadow_striders", 5),
            ("resonance_ring", 5), ("stalkers_cowl", 5), ("resonance_treads", 5),
            ("diamond_armor", 5), ("djarns_ring", 4),
            ("blood_sword", 3), ("masamune", 2), ("fiery_avenger", 2),
            ("holy_avenger", 2), ("vorpal_sword", 2), ("staff_magi", 2),
            ("dragon_scale", 3), ("ethereal_plate", 3), ("genji_armor", 3),
            ("hermes_boots", 2), ("genji_boots", 2), ("genji_helm", 2),
            ("ogre_gauntlets", 2), ("giant_belt", 2), ("mox_pearl", 1),
            ("resonance_bow", 3), ("aeridorian_axe", 3), ("soulfire", 3),
            ("mjolnir", 3), ("full_plate", 3), ("aeridorian_plate", 3),
            ("shadowweave_mask", 3), ("resonance_crown", 3), ("aeridorian_greaves", 3),
            ("displacement_cloak", 3),
        ],
        "boss": [
            ("elixir", 30), ("phoenix_down", 15), ("gilded_mushroom", 20),
            ("void_helm", 10), ("void_striders", 10), ("void_band", 10),
            ("masamune", 5), ("fiery_avenger", 5), ("rubicite_armor", 5),
            ("excalibur_ff", 5), ("ragnarok_ff", 5), ("ultima_weapon", 4),
            ("adamantine_plate", 5), ("brilliance_helm", 5), ("crown_stars", 5),
            ("seven_league_boots", 5), ("archmage_robe", 5), ("black_lotus", 2),
            ("void_blade", 5), ("elaras_token", 1),
        ],
    }

    table = tables.get(tier, tables["medium"])
    total_weight = sum(w for _, w in table)
    roll = secrets.randbelow(total_weight)

    current = 0
    for item_name, weight in table:
        current += weight
        if roll < current:
            return None if item_name == "none" else item_name
    return None
