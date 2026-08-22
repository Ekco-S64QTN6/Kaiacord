"""
Item drops for monster kills based on their difficulty tier.
Keys match equipment_registry.py so items can be used/sold/equipped.

Loot is split into two independent pools:
  - get_gear_loot(tier)       — weapons, armor, headgear, boots, accessories
  - get_consumable_loot(tier)  — potions, herbs, ingredients, misc items

Normal creatures roll once on each table.
Bosses get 1 guaranteed gear + 40% second gear + 1 consumable.
"""
import secrets
from typing import Optional


def get_gear_loot(tier: str) -> Optional[str]:
    """Returns a gear item key or None."""
    tables = {
        "trivial": [
            ("none", 40),
            # Tier 1 generic
            ("rusty_dagger", 8), ("wooden_staff", 6), ("wooden_club", 6),
            ("shortbow", 5), ("hand_axe", 5), ("travelers_cloak", 6),
            ("worn_cap", 5), ("worn_boots", 5), ("bronze_helm", 4), ("bronze_sabatons", 4),
            ("copper_ring", 4),
            # Tier 1 class-specific
            ("rusted_greatsword", 3), ("hunting_bow", 3), ("skinning_knife", 2),
            ("apprentice_wand", 2), ("novice_focus", 2), ("shiv", 3), ("throwing_knife", 3),
            ("acolyte_mace", 2), ("iron_flail", 2),
            ("iron_plating", 2), ("rangers_vest", 2), ("cutpurse_leathers", 2),
            ("novice_robes", 2), ("acolyte_vestments", 2),
            ("soldiers_cap", 2), ("ranger_hat", 2), ("shadow_cap", 2),
            ("ember_cowl", 2), ("novice_hood", 2),
            ("warriors_bracer", 3), ("scouts_bracer", 3), ("scholars_bracelet", 2),
            # Tier 2 rare
            ("iron_sword", 3), ("spear", 2), ("leather_armor", 3),
        ],
        "easy": [
            ("none", 25),
            # Tier 1 generics
            ("bronze_armor", 5), ("bronze_helm", 4), ("bronze_sabatons", 4),
            ("iron_helm", 4), ("mages_cap", 4), ("heavy_boots", 4), ("soft_slippers", 4),
            ("scouts_hood", 5), ("trackers_boots", 5), ("copper_ring", 5),
            # Tier 2 generics
            ("iron_staff", 4), ("iron_sword", 5), ("spear", 4), ("crossbow", 4),
            ("battle_axe", 4), ("mages_robe", 4), ("leather_armor", 5),
            ("warriors_bracer", 4), ("scouts_bracer", 4), ("scholars_bracelet", 4),
            ("horned_helmet", 3), ("sages_hat", 3),
            ("studded_leather", 4), ("chainmail", 3), ("silken_robe", 3), ("black_garb", 3),
            ("iron_ring", 3), ("oak_bracelet", 3),
            # Tier 2 class-specific
            ("iron_greatsword", 3), ("iron_halberd", 3), ("composite_bow", 3),
            ("forester_shortbow", 3), ("crystal_wand", 3), ("resonance_focus", 3),
            ("shadow_blade", 3), ("assassin_stiletto", 3),
            ("shrine_warhammer", 3), ("silver_mace", 3),
            ("battle_plate", 3), ("scouts_leathers", 3), ("shadow_garb", 3),
            ("channeler_robes", 3), ("shrine_chainmail", 3),
            ("battle_visor", 3), ("camouflage_cowl", 3), ("phantom_hood", 3),
            ("channeler_hat", 3), ("priest_mitre", 3),
            ("iron_greaves", 3), ("trail_boots", 3), ("resonance_sandals", 3),
            ("blessed_sandals", 3),
            ("iron_gauntlets", 3), ("quiver_bracer", 3), ("shadow_ring", 3),
            ("arcane_focus_ring", 3), ("holy_symbol", 3), ("crystal_bracelet", 3),
            # Tier 3 rare
            ("mithral_shirt", 2), ("flametongue", 1), ("winged_boots", 1),
        ],
        "medium": [
            ("none", 12),
            # Tier 2 generics
            ("leather_coif", 5), ("shadow_treads", 4), ("iron_ring", 4), ("oak_bracelet", 4),
            ("studded_leather", 4), ("chainmail", 4), ("black_garb", 3), ("fur_cloak", 3),
            ("steel_visor", 3), ("silken_cowl", 3), ("iron_shod_boots", 3),
            ("foresters_boots", 3), ("ley_walkers", 3), ("crystal_bracelet", 3),
            # Tier 3 generics
            ("longsword", 5), ("steel_blade", 5), ("silken_robe", 4),
            ("flame_sword", 3), ("ice_brand", 3), ("flametongue", 3), ("frostbrand", 3),
            ("mithral_shirt", 3), ("flame_helm", 4), ("flame_greaves", 4),
            ("executioner_hood", 3), ("striding_boots", 3),
            ("serpentine_bracer", 3), ("ring_protection", 3), ("periapt_poison", 3),
            ("silver_ring", 3), ("gold_ring", 2),
            # Tier 3 class-specific
            ("steel_greatsword", 3), ("war_halberd", 3),
            ("whisperwood_recurve", 3), ("hunters_knife", 3),
            ("aeridor_wand", 3), ("elder_orb", 3),
            ("gutting_knife", 3), ("obsidian_dagger", 3),
            ("temple_hammer", 3), ("sanctuary_mace", 3),
            ("knights_plate", 3), ("whisperwood_garb", 3), ("phantom_weave", 3),
            ("invoker_vestment", 3), ("cleric_plate", 3),
            ("warlord_helm", 3), ("whisperwood_cowl", 3), ("void_cowl", 3),
            ("invoker_circlet", 3), ("temple_circlet", 3),
            ("battle_greaves", 3), ("whisper_stride", 3), ("arcane_walkers", 3),
            ("shrine_greaves", 3), ("whisperwood_boots", 3),
            ("battle_bracer", 3), ("hunters_charm", 3), ("phantom_bracer", 3),
            ("resonance_orb_acc", 3), ("blessed_rosary", 3),
            # Tier 4 rare
            ("diamond_armor", 1), ("masamune", 1), ("circlet_persuasion", 2),
        ],
        "hard": [
            ("none", 6),
            # Tier 3 generics
            ("siege_helm", 4), ("whisperwood_boots", 4), ("silver_ring", 5),
            ("aeridor_bangle", 5), ("gold_ring", 4),
            ("flame_mail", 4), ("ice_armor", 4), ("defender", 3),
            ("diamond_helm", 3), ("diamond_boots", 3),
            ("circlet_persuasion", 3), ("ribbon", 3),
            ("tricklebrook_charm", 3),
            # Tier 3 class-specific
            ("knights_plate", 3), ("whisperwood_garb", 3), ("phantom_weave", 3),
            ("invoker_vestment", 3), ("cleric_plate", 3),
            ("warlord_helm", 3), ("whisperwood_cowl", 3),
            ("battle_greaves", 3), ("whisper_stride", 3),
            ("battle_bracer", 3), ("hunters_charm", 3), ("phantom_bracer", 3),
            ("resonance_orb_acc", 3), ("blessed_rosary", 3),
            # Spine Upper Set (T4)
            ("miners_rebellion_pick", 2), ("soot_stained_cleaver", 2), ("bone_woven_bow", 2),
            ("echo_chime_focus", 2), ("crypt_warden_mace", 2),
            ("rusted_ironclad_plate", 2), ("scouts_bone_leather", 2), ("ash_woven_robes", 2),
            ("tunnel_runners_garb", 2), ("deep_chaplains_vestment", 2),
            ("slag_crusted_helm", 2), ("tunnel_scouts_hood", 2), ("scholars_ashen_cowl", 2),
            ("cowl_of_the_blind_leech", 2), ("deep_chaplains_mitre", 2),
            ("ironclad_stompers", 2), ("tunnel_runners_boots", 2), ("emberwalk_slippers", 2),
            ("striders_of_the_abyss", 2), ("deep_chaplains_sandals", 2),
            ("pendant_of_the_lost_scout", 2), ("bone_tooth_necklace", 2),
            ("resonance_warped_ring", 2), ("lockpicks_of_the_damned", 2), ("deep_chaplains_rosary", 2),
            ("sun_blade", 3), ("disruption_mace", 3), ("boots_speed", 2),
            ("bracers_defense", 2), ("amulet_health", 2),
            ("resonance_staff", 3), ("shining_staff", 3), ("yoichi_bow", 3),
            ("ghoulbane", 3), ("ykesha_sword", 3), ("arcane_vestment", 3),
            ("half_plate", 3), ("arcane_circlet", 3), ("gold_hairpin", 3),
            ("wardens_greaves", 3), ("resonance_ring", 2),
            # Tier 4 class-specific
            ("aeridorian_greatsword", 2), ("champion_spear", 2),
            ("aeridor_longbow", 2), ("moonbow", 2),
            ("void_orb", 2), ("the_whispering_wand", 2),
            ("whisper_blade", 2), ("the_quiet_death", 2),
            ("dawn_hammer", 2), ("silent_one_mace", 2),
            ("warlord_plate", 2), ("ghost_leather", 2), ("void_cloth", 2),
            ("void_vestment", 2), ("saint_plate", 2),
            ("champion_helm", 2), ("hunters_visor", 2), ("arcanist_circlet", 2),
            ("ghost_mask", 2), ("high_priest_mitre", 2),
            ("warlord_greaves", 2), ("silent_runner", 2), ("void_walkers", 2),
            ("saints_boots", 2),
            ("warlords_gauntlets", 2), ("forest_ring", 2), ("void_focus", 2),
            ("void_ring", 2), ("saints_medallion", 2),
            ("ogre_gauntlets", 2), ("djarns_ring", 2),
        ],
        "deadly": [
            # Tier 4 generics
            ("aeridorian_helm", 5), ("shadow_striders", 5),
            ("resonance_ring", 5), ("stalkers_cowl", 5), ("resonance_treads", 5),
            ("diamond_armor", 5), ("djarns_ring", 4),
            ("blood_sword", 3), ("masamune", 3), ("fiery_avenger", 3),
            ("aeridorian_axe", 4), ("soulfire", 3),
            ("full_plate", 3), ("aeridorian_plate", 3),
            ("shadowweave_mask", 3), ("resonance_crown", 3), ("aeridorian_greaves", 3),
            ("displacement_cloak", 3), ("winged_boots", 3),
            # Tier 4 class-specific
            ("aeridorian_greatsword", 3), ("champion_spear", 3),
            ("aeridor_longbow", 3), ("moonbow", 3),
            ("void_orb", 3), ("the_whispering_wand", 3),
            ("whisper_blade", 3), ("the_quiet_death", 3),
            ("dawn_hammer", 3), ("silent_one_mace", 3),
            ("warlord_plate", 3), ("ghost_leather", 3), ("void_cloth", 3),
            ("void_vestment", 3), ("saint_plate", 3),
            ("champion_helm", 3), ("hunters_visor", 3), ("arcanist_circlet", 3),
            ("ghost_mask", 3), ("high_priest_mitre", 3),
            ("warlord_greaves", 3), ("silent_runner", 3), ("void_walkers", 3),
            ("saints_boots", 3),
            ("warlords_gauntlets", 3), ("forest_ring", 3), ("void_focus", 3),
            ("void_ring", 3), ("saints_medallion", 3),
            # Spine Lower Set (T5)
            ("heart_forged_greatsword", 2), ("void_touched_longbow", 2), ("aeridorian_spine_staff", 2),
            ("elaras_betrayal_dagger", 2), ("forge_masters_hammer", 2),
            ("flesh_forged_cuirass", 2), ("deep_stalkers_hide", 2), ("the_vessels_mantle", 2),
            ("eyeless_horrors_skin", 2), ("core_chaplains_raiment", 2),
            ("heartstone_visor", 2), ("void_stalkers_cowl", 2), ("resonance_diadem_spine", 2),
            ("lurking_shadows_hood", 2), ("core_chaplains_circlet", 2),
            ("heartstone_greaves", 2), ("abyssal_striders", 2), ("pulse_walkers_treads", 2),
            ("shadow_step_boots", 2), ("core_chaplains_sandals", 2),
            ("tithe_collectors_signet", 2), ("deep_watcher_charm", 2), ("crystalline_focus_ring", 2),
            ("marrow_bite_ring", 2), ("vessels_rosary", 2),
            ("holy_avenger", 3), ("vorpal_sword", 3), ("staff_magi", 3), ("stardust_rod", 3),
            ("dragon_scale", 3), ("ethereal_plate", 3), ("genji_armor", 3),
            ("hermes_boots", 2), ("genji_boots", 2), ("genji_helm", 2),
            ("ogre_gauntlets", 2), ("giant_belt", 2), ("mox_pearl", 1),
            ("mjolnir", 3), ("resonance_bow", 3),
            # Tier 5 class-specific
            ("spine_cleaver", 2), ("champions_legacy", 2),
            ("silent_stalker_bow", 2), ("null_scepter", 2),
            ("voidstep_blade", 2), ("the_last_laugh", 2),
            ("morvenna_flail", 2), ("voice_of_dawn", 2),
            ("champion_plate", 2), ("forest_sovereign_armor", 2),
            ("void_mantle", 2), ("arcanist_shroud", 2),
            ("voice_of_silence_armor", 2),
            ("the_iron_crown", 2), ("forest_crown", 2), ("void_crown", 2),
            ("the_last_face", 2), ("silence_crown", 2),
            ("champion_sabatons", 2), ("forest_stride", 2), ("silence_treads", 2),
            ("champion_bracers", 2), ("silence_sigil", 2),
            # Tier 6
            ("ruinbreaker", 1), ("oathkeeper", 1), ("whisperwind_bow", 1),
            ("resonance_spire", 1), ("nightfall_edge", 1), ("dawnforged_mace", 1),
            ("dragon_slayer", 1), ("stormcaller", 1),
            ("dragonscale_plate", 1), ("whisperwood_aegis", 1), ("resonance_vestment", 1),
            ("shadowmeld_garb", 1), ("dawn_raiment", 1), ("aeridorian_warplate", 1),
            ("dragonscale_helm", 1), ("whisperwood_crown", 1), ("resonance_diadem", 1),
            ("dragonscale_greaves", 1), ("nightfall_treads", 1),
            ("dragonscale_bracer", 1), ("whisperwood_talisman", 1),
        ],
        "boss": [
            # Tier 4 high-end
            ("masamune", 5), ("fiery_avenger", 5), ("sun_blade", 4),
            ("displacement_cloak", 4), ("ogre_gauntlets", 4),
            # Tier 5 generics
            ("rubicite_armor", 5), ("excalibur_ff", 5), ("ragnarok_ff", 5),
            ("ultima_weapon", 4), ("adamantine_plate", 5),
            ("brilliance_helm", 5), ("crown_stars", 5),
            ("seven_league_boots", 5), ("archmage_robe", 5), ("black_lotus", 2),
            ("void_blade", 5), ("void_helm", 6), ("void_striders", 6),
            ("void_band", 6), ("dragon_scale", 5), ("ethereal_plate", 5),
            ("genji_armor", 5), ("genji_boots", 4), ("genji_helm", 4),
            ("hermes_boots", 4), ("mox_pearl", 3),
            ("holy_avenger", 5), ("vorpal_sword", 5), ("staff_magi", 5), ("stardust_rod", 5),
            ("mjolnir", 4), ("soulfire", 4),
            # Tier 5 class-specific
            ("spine_cleaver", 4), ("champions_legacy", 4),
            ("silent_stalker_bow", 4), ("null_scepter", 4),
            ("voidstep_blade", 4), ("the_last_laugh", 4),
            ("morvenna_flail", 4), ("voice_of_dawn", 4),
            ("champion_plate", 4), ("forest_sovereign_armor", 4),
            ("void_mantle", 4), ("arcanist_shroud", 4),
            ("voice_of_silence_armor", 4),
            ("the_iron_crown", 4), ("forest_crown", 4), ("void_crown", 4),
            ("the_last_face", 4), ("silence_crown", 4),
            ("champion_sabatons", 4), ("forest_stride", 4), ("silence_treads", 4),
            ("champion_bracers", 4), ("silence_sigil", 4),
            ("giant_belt", 4),
            ("elaras_token", 1),
            # Spine Lower Set (Boss drops)
            ("heart_forged_greatsword", 3), ("void_touched_longbow", 3), ("aeridorian_spine_staff", 3),
            ("elaras_betrayal_dagger", 3), ("forge_masters_hammer", 3),
            ("flesh_forged_cuirass", 3), ("the_vessels_mantle", 3), ("eyeless_horrors_skin", 3),
            ("tithe_collectors_signet", 3), ("marrow_bite_ring", 3), ("vessels_rosary", 3),
            ("ruinbreaker", 3), ("oathkeeper", 3), ("whisperwind_bow", 3),
            ("predators_fang", 3), ("resonance_spire", 3), ("aethervane", 3),
            ("nightfall_edge", 3), ("deaths_whisper", 3), ("dawnforged_mace", 3),
            ("silence_speaker", 3), ("dragon_slayer", 3), ("stormcaller", 3),
            ("dragonscale_plate", 3), ("whisperwood_aegis", 3), ("resonance_vestment", 3),
            ("shadowmeld_garb", 3), ("dawn_raiment", 3), ("aeridorian_warplate", 3),
            ("dragonscale_helm", 3), ("whisperwood_crown", 3), ("resonance_diadem", 3),
            ("nightfall_mask", 3), ("dawn_circlet", 3),
            ("dragonscale_greaves", 3), ("whisperwood_stride", 3),
            ("nightfall_treads", 3), ("dawn_sabatons", 3),
            ("dragonscale_bracer", 3), ("whisperwood_talisman", 3),
            ("resonance_focus_t6", 3), ("nightfall_ring", 3),
            # Tier 7 (rare from bosses)
            ("worldsplitter", 1), ("morvenna_scythe", 1), ("starfall_bow", 1),
            ("resonance_singularity", 1), ("aeridorian_cipher", 1),
            ("phantom_reaver", 1), ("voice_of_the_silent_ones", 1),
            ("aeridorian_terminus", 1), ("crown_of_ruin", 1), ("the_end", 1),
            ("worldroot_plate", 1), ("voidweave_robe", 1), ("silent_ones_vestment", 1),
            ("mythril_shadowmail", 1), ("aeridorian_aegis", 1),
            ("worldroot_crown", 1), ("voidweave_cowl", 1), ("silent_ones_halo", 1),
            ("mythril_visor", 1), ("aeridorian_crown", 1),
            ("worldroot_greaves", 1), ("voidwalker_boots", 1),
            ("silent_ones_sandals", 1), ("aeridorian_striders", 1),
            ("worldroot_signet", 1), ("voidweave_band", 1),
            ("silent_ones_medallion", 1), ("aeridorian_sigil", 1),
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


def get_consumable_loot(tier: str) -> Optional[str]:
    """Returns a consumable/ingredient item key or None."""
    tables = {
        "trivial": [
            ("none", 20),
            ("healing_herb", 20), ("bandage", 15), ("honey_sap", 22),
            ("eye_drops", 8), ("torch", 6),
            ("mognet_letter", 5),
            ("pearl", 8), ("topaz", 5), ("peridot", 3),
        ],
        "easy": [
            ("none", 10),
            ("healing_herb", 14), ("bandage", 12), ("tonic", 8), ("hi_potion", 6),
            ("blood_thistle", 18), ("silver_moss", 14), ("honey_sap", 14),
            ("lucky_charm", 8),
            ("pearl", 6), ("topaz", 5), ("peridot", 4), ("emerald", 3), ("opal", 2),
        ],
        "medium": [
            ("none", 8),
            ("tonic", 14), ("hi_potion", 10), ("healing_herb", 8), ("bandage", 8),
            ("silver_moss", 16), ("dire_root", 14), ("blood_thistle", 14),
            ("silverleaf", 6), ("honey_sap", 10),
            ("tonberry_knife", 3), ("aeridor_shard", 3),
            ("ether", 16),
            ("emerald", 5), ("opal", 4), ("black_pearl", 2), ("fire_opal", 1),
        ],
        "hard": [
            ("none", 4),
            ("tonic", 10), ("elixir", 8), ("hi_potion", 8),
            ("aeridor_shard", 14), ("dire_root", 16), ("silver_moss", 12),
            ("silverleaf", 10), ("blood_thistle", 10), ("honey_sap", 8),
            ("phoenix_down", 3), ("ether", 9),
            ("opal", 3), ("black_pearl", 5), ("fire_opal", 4),
            ("star_ruby", 3), ("fire_emerald", 2),
        ],
        "deadly": [
            ("tonic", 6), ("elixir", 12), ("phoenix_down", 8),
            ("aeridor_shard", 16), ("dire_root", 12), ("gilded_mushroom", 10),
            ("silverleaf", 8), ("blood_thistle", 10), ("silver_moss", 10), ("honey_sap", 8),
            ("ether", 12),
            ("fire_emerald", 4), ("sapphire", 3), ("ruby", 2),
            ("star_ruby", 3), ("jacinth", 2),
        ],
        "boss": [
            ("elixir", 25), ("phoenix_down", 18), ("gilded_mushroom", 22),
            ("dire_root", 10), ("silverleaf", 6), ("blood_thistle", 8), ("silver_moss", 8),
            ("honey_sap", 6),
            ("ether", 13),
            ("sapphire", 5), ("ruby", 4), ("jacinth", 3),
            ("black_sapphire", 2), ("diamond", 2), ("blue_diamond", 1),
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


# ── Backward-compatible wrapper ──────────────────────────────────────────────
def get_loot(tier: str) -> Optional[str]:
    """Legacy wrapper — returns a gear item. Use get_gear_loot / get_consumable_loot instead."""
    return get_gear_loot(tier)
