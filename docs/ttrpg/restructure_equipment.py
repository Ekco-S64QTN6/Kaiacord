#!/usr/bin/env python3
"""
Equipment Registry Restructure - handles single-line AND multi-line item dicts.
Usage: python restructure_equipment.py src.py dst.py
"""
import re, sys

PRICES = {
    # T1 (8-75g)
    "rusty_dagger":12,"wooden_club":8,"wooden_staff":18,"shortbow":28,
    "rusty_hand_axe":22,"rusty_stiletto":24,"rusty_mace":20,
    "rusted_greatsword":20,"hunting_bow":25,"skinning_knife":14,
    "apprentice_wand":16,"novice_focus":12,"shiv":8,"throwing_knife":14,
    "acolyte_mace":18,"iron_flail":16,
    "travelers_cloak":8,"leather_armor":28,"mages_robe":20,"bronze_armor":38,
    "fur_cloak":22,"iron_plating":35,"rangers_vest":25,"cutpurse_leathers":20,
    "novice_robes":14,"acolyte_vestments":20,
    "worn_cap":6,"iron_helm":24,"scouts_hood":20,"mages_cap":16,
    "bronze_helm":22,"soldiers_cap":18,"ranger_hat":18,"shadow_cap":15,
    "ember_cowl":15,"novice_hood":15,
    "worn_boots":8,"heavy_boots":26,"trackers_boots":22,"soft_slippers":16,
    "bronze_sabatons":24,
    "copper_ring":12,"warriors_bracer":25,"scouts_bracer":20,"scholars_bracelet":16,
    # T2 (250-420g)
    "iron_sword":260,"iron_staff":255,"iron_spear":270,"crossbow":295,
    "iron_battle_axe":280,"iron_dirk":260,"iron_morning_star":265,
    "iron_greatsword":285,"iron_halberd":275,"composite_bow":290,
    "forester_shortbow":268,"crystal_wand":272,"resonance_focus":278,
    "shadow_blade":295,"assassin_stiletto":272,"shrine_warhammer":272,
    "silver_mace":285,
    "studded_leather":258,"chainmail":295,"silken_robe":262,"black_garb":280,
    "battle_plate":290,"scouts_leathers":268,"shadow_garb":275,
    "channeler_robes":262,"shrine_chainmail":278,
    "steel_visor":272,"leather_coif":258,"silken_cowl":262,"horned_helmet":268,
    "sages_hat":272,"battle_visor":268,"camouflage_cowl":260,"phantom_hood":258,
    "channeler_hat":258,"priest_mitre":262,
    "iron_shod_boots":268,"shadow_treads":262,"foresters_boots":258,
    "ley_walkers":258,"iron_greaves":272,"trail_boots":260,"resonance_sandals":258,
    "blessed_sandals":260,
    "iron_ring":258,"oak_bracelet":262,"crystal_bracelet":262,
    "iron_gauntlets":268,"quiver_bracer":260,"shadow_ring":258,
    "arcane_focus_ring":260,"holy_symbol":262,
    # T3 (750-1300g)
    "steel_longsword":800,"steel_dagger":950,"flame_sword":870,"ice_brand":895,
    "flame_scepter":980,"ghoulbane":1050,"flametongue":1150,"frostbrand":1150,
    "whisperwood_recurve":820,"hunters_knife":800,"aeridor_wand":920,
    "elder_orb":895,"gutting_knife":975,"obsidian_dagger":895,
    "temple_hammer":820,"sanctuary_mace":975,"steel_greatsword":845,"war_halberd":870,
    "half_plate":920,"flame_mail":970,"ice_armor":970,"mithral_shirt":1150,
    "knights_plate":900,"whisperwood_garb":890,"phantom_weave":910,
    "invoker_vestment":895,"cleric_plate":920,
    "siege_helm":840,"stalkers_cowl":820,"arcane_circlet":830,"flame_helm":835,
    "gold_hairpin":820,"ribbon":920,"executioner_hood":815,
    "circlet_persuasion":975,"warlord_helm":860,"whisperwood_cowl":840,
    "void_cowl":850,"invoker_circlet":835,"temple_circlet":840,
    "wardens_greaves":840,"whisperwood_boots":830,"resonance_treads":835,
    "flame_greaves":825,"striding_boots":820,"battle_greaves":850,
    "whisper_stride":835,"arcane_walkers":830,"shrine_greaves":835,
    "silver_ring":840,"tricklebrook_charm":820,"aeridor_bangle":870,
    "serpentine_bracer":850,"gold_ring":865,"ring_protection":920,
    "periapt_poison":840,"battle_bracer":860,"hunters_charm":855,
    "phantom_bracer":850,"resonance_orb_acc":860,"blessed_rosary":855,
    # T4 (2200-3600g)
    "resonance_staff":2400,"resonance_bow":2500,"aeridorian_axe":3000,
    "masamune":3400,"fiery_avenger":2800,"blood_sword":2600,"shining_staff":2600,
    "yoichi_bow":2800,"sun_blade":3600,"ykesha_sword":2500,"disruption_mace":3000,
    "aeridorian_greatsword":3000,"champion_spear":2700,"aeridor_longbow":2700,
    "moonbow":3200,"void_orb":2800,"the_whispering_wand":3100,
    "whisper_blade":2700,"the_quiet_death":3100,"dawn_hammer":2900,
    "silent_one_mace":2700,
    "full_plate":3000,"diamond_armor":2700,"arcane_vestment":2400,
    "aeridorian_plate":3400,"warlord_plate":3000,"ghost_leather":2800,
    "void_cloth":2900,"void_vestment":3000,"saint_plate":3200,
    "aeridorian_helm":2800,"shadowweave_mask":2700,"resonance_crown":2800,
    "diamond_helm":2700,"champion_helm":2900,"hunters_visor":2800,
    "arcanist_circlet":2800,"ghost_mask":2700,"high_priest_mitre":2900,
    "aeridorian_greaves":2900,"shadow_striders":2800,"diamond_boots":2800,
    "winged_boots":3200,"boots_speed":3000,"warlord_greaves":2900,
    "silent_runner":2800,"void_walkers":2800,"saints_boots":2900,
    "resonance_ring":2900,"elaras_token":0,"djarns_ring":3100,
    "bracers_defense":2900,"amulet_health":2700,"ogre_gauntlets":3400,
    "displacement_cloak":3700,"warlords_gauntlets":2900,"forest_ring":2800,
    "void_focus":2900,"void_ring":2800,"saints_medallion":2900,
    # T5 (5500-55000g)
    "void_blade":6500,"holy_avenger":7500,"vorpal_sword":8500,"staff_magi":7500,
    "soulfire":8000,"excalibur_ff":9500,"ragnarok_ff":9000,"ultima_weapon":13000,
    "mjolnir":7800,"spine_cleaver":8000,"champions_legacy":7000,
    "silent_stalker_bow":7500,"null_scepter":7800,"voidstep_blade":8400,
    "the_last_laugh":7300,"morvenna_flail":7500,"voice_of_dawn":8500,
    "rubicite_armor":8000,"dragon_scale":9500,"ethereal_plate":11000,
    "archmage_robe":9500,"genji_armor":9000,"adamantine_plate":12000,
    "champion_plate":8500,"forest_sovereign_armor":8300,"void_mantle":7800,
    "arcanist_shroud":7600,"voice_of_silence_armor":9000,
    "void_helm":7000,"brilliance_helm":7500,"crown_stars":7300,"genji_helm":7000,
    "the_iron_crown":8000,"forest_crown":7500,"void_crown":7500,
    "the_last_face":7500,"silence_crown":8000,
    "seven_league_boots":7500,"void_striders":7500,"hermes_boots":8000,
    "genji_boots":8500,"champion_sabatons":8000,"forest_stride":7800,"silence_treads":8000,
    "void_band":7500,"mox_pearl":13000,"black_lotus":55000,"giant_belt":8000,
    "champion_bracers":8000,"silence_sigil":8000,
}

DROPPABLE_ONLY = {
    # T2 locked behind combat
    "shadow_blade","assassin_stiletto","silver_mace",
    "scouts_leathers","battle_plate","battle_visor","phantom_hood",
    "iron_greaves","shadow_treads","iron_gauntlets","shadow_ring",
    # T3 mostly droppable
    "steel_dagger","ice_brand","ghoulbane","flametongue","frostbrand",
    "war_halberd","gutting_knife","obsidian_dagger","sanctuary_mace","elder_orb",
    "flame_mail","ice_armor","mithral_shirt","phantom_weave",
    "ribbon","circlet_persuasion","stalkers_cowl","void_cowl","warlord_helm",
    "whisper_stride","tricklebrook_charm","aeridor_bangle","serpentine_bracer",
    "gold_ring","ring_protection","periapt_poison","phantom_bracer",
    # T4 all droppable
    "resonance_staff","resonance_bow","aeridorian_axe","masamune",
    "fiery_avenger","blood_sword","shining_staff","yoichi_bow","sun_blade",
    "ykesha_sword","disruption_mace","aeridorian_greatsword","champion_spear",
    "aeridor_longbow","moonbow","void_orb","the_whispering_wand",
    "whisper_blade","the_quiet_death","dawn_hammer","silent_one_mace",
    "full_plate","diamond_armor","arcane_vestment","aeridorian_plate",
    "warlord_plate","ghost_leather","void_cloth","void_vestment","saint_plate",
    "aeridorian_helm","shadowweave_mask","resonance_crown","diamond_helm",
    "champion_helm","hunters_visor","arcanist_circlet","ghost_mask","high_priest_mitre",
    "aeridorian_greaves","shadow_striders","diamond_boots","winged_boots","boots_speed",
    "warlord_greaves","silent_runner","void_walkers","saints_boots",
    "resonance_ring","elaras_token","djarns_ring","bracers_defense","amulet_health",
    "ogre_gauntlets","displacement_cloak","warlords_gauntlets","forest_ring",
    "void_focus","void_ring","saints_medallion",
    # T5 all droppable
    "void_blade","holy_avenger","vorpal_sword","staff_magi","soulfire",
    "excalibur_ff","ragnarok_ff","ultima_weapon","mjolnir",
    "spine_cleaver","champions_legacy","silent_stalker_bow","null_scepter",
    "voidstep_blade","the_last_laugh","morvenna_flail","voice_of_dawn",
    "rubicite_armor","dragon_scale","ethereal_plate","archmage_robe",
    "genji_armor","adamantine_plate","champion_plate","forest_sovereign_armor",
    "void_mantle","arcanist_shroud","voice_of_silence_armor",
    "void_helm","brilliance_helm","crown_stars","genji_helm","the_iron_crown",
    "forest_crown","void_crown","the_last_face","silence_crown",
    "seven_league_boots","void_striders","hermes_boots","genji_boots",
    "champion_sabatons","forest_stride","silence_treads",
    "void_band","mox_pearl","black_lotus","giant_belt","champion_bracers","silence_sigil",
}

HEMLOCK_WEAPONS   = ['shortbow','rusty_hand_axe','rusty_stiletto','rusty_mace','wooden_staff','hunting_bow','skinning_knife','rusted_greatsword','apprentice_wand','novice_focus','shiv','throwing_knife','iron_flail','acolyte_mace']
HEMLOCK_ARMOR     = ['leather_armor','mages_robe','bronze_armor','fur_cloak','iron_plating','rangers_vest','cutpurse_leathers','novice_robes','acolyte_vestments']
HEMLOCK_HEADGEAR  = ['iron_helm','scouts_hood','mages_cap','bronze_helm','soldiers_cap','ranger_hat','shadow_cap','ember_cowl','novice_hood']
HEMLOCK_BOOTS     = ['worn_boots','heavy_boots','trackers_boots','soft_slippers','bronze_sabatons']
HEMLOCK_ACC       = ['copper_ring','warriors_bracer','scouts_bracer','scholars_bracelet']
HEMLOCK_CONS      = ['healing_herb','bandage','tonic','torch','antidote']

NEW_CARAVAN_FUNC = '''\
def get_caravan_stock():
    """
    Returns Tier 2 and Tier 3 purchasable (non-droppable) items for the Caravan.
    Items with droppable_only=True must be looted from monsters.
    """
    gear_keys = []
    consumable_keys = []
    for reg in (WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES):
        for k, v in reg.items():
            if v.get("tier") in (2, 3) and not v.get("droppable_only"):
                gear_keys.append(k)
    for k, v in CONSUMABLES.items():
        if v.get("tier") in (2, 3):
            consumable_keys.append(k)
    return gear_keys, consumable_keys
'''

NEW_HEMLOCK = (
    f'HEMLOCK_STOCK_WEAPONS = {HEMLOCK_WEAPONS!r}\n'
    f'HEMLOCK_STOCK_ARMOR   = {HEMLOCK_ARMOR!r}\n'
    f'HEMLOCK_STOCK_HEADGEAR = {HEMLOCK_HEADGEAR!r}\n'
    f'HEMLOCK_STOCK_BOOTS    = {HEMLOCK_BOOTS!r}\n'
    f'HEMLOCK_STOCK_ACCESSORIES = {HEMLOCK_ACC!r}\n'
    f'HEMLOCK_STOCK_CONSUMABLES = {HEMLOCK_CONS!r}\n'
)


def process(src: str) -> str:
    # ── Pass 1: Update "value": N for single-line item entries ───────────────
    # Handles: `    "key": {"name": ..., "value": 35, ...},`
    def replace_value_inline(m):
        key = m.group(1)
        if key not in PRICES:
            return m.group(0)
        original = m.group(0)
        updated = re.sub(r'"value"\s*:\s*\d+', f'"value": {PRICES[key]}', original)
        return updated

    # Match a complete single-line item entry
    src = re.sub(
        r'^ {4}"([a-z0-9_]+)"\s*:\s*\{[^\n]+\},?$',
        replace_value_inline,
        src,
        flags=re.MULTILINE,
    )

    # ── Pass 2: Update "value": N for multi-line item entries ─────────────────
    # Handles blocks like:
    #     "key": {
    #         ..., "value": N, ...
    #     },
    for key, price in PRICES.items():
        # Find multi-line dict starting with this key
        pattern = rf'("    "{re.escape(key)}"\s*:\s*\{{)([^}}]*?)("value"\s*:\s*)\d+([^}}]*?\}})'
        # simpler: just do value replacement when key is in context
        pass  # handled below with stateful pass

    # Stateful multi-line pass for value updates
    lines = src.splitlines()
    out   = []
    cur_key   = None
    depth     = 0
    key_pat   = re.compile(r'^ {4}"([a-z0-9_]+)"\s*:\s*\{')

    for line in lines:
        if depth == 0:
            m = key_pat.match(line)
            if m:
                cur_key = m.group(1)
                depth = line.count('{') - line.count('}')
                # single-line: depth already back to 0 after count — handled by pass1
                # multi-line: depth > 0, keep tracking
                out.append(line)
                continue

        if cur_key and depth > 0:
            depth += line.count('{') - line.count('}')
            if '"value":' in line and cur_key in PRICES:
                line = re.sub(r'"value"\s*:\s*\d+', f'"value": {PRICES[cur_key]}', line)
            if depth == 0:
                cur_key = None
        out.append(line)

    src = '\n'.join(out)

    # ── Pass 3: Inject droppable_only into single-line entries ───────────────
    def inject_droppable_single(m):
        key = m.group(1)
        if key not in DROPPABLE_ONLY:
            return m.group(0)
        body = m.group(0)
        if 'droppable_only' in body:
            return body
        # Insert before closing }
        return re.sub(r'\}(\s*,?\s*)$', r', "droppable_only": True}\1', body)

    src = re.sub(
        r'^ {4}"([a-z0-9_]+)"\s*:\s*\{[^\n]+\},?$',
        inject_droppable_single,
        src,
        flags=re.MULTILINE,
    )

    # ── Pass 4: Inject droppable_only into multi-line entries ────────────────
    lines = src.splitlines()
    out   = []
    cur_key = None
    depth   = 0

    for line in lines:
        if depth == 0:
            m = key_pat.match(line)
            if m:
                cur_key = m.group(1)
                depth = line.count('{') - line.count('}')
                out.append(line)
                continue

        if cur_key and depth > 0:
            depth += line.count('{') - line.count('}')
            if depth == 0 and cur_key in DROPPABLE_ONLY:
                # This is the closing line of a multi-line dict
                # Insert droppable_only on line before it if not already present
                if out and 'droppable_only' not in '\n'.join(out[-5:]):
                    # Get indent of closing line
                    indent = len(line) - len(line.lstrip())
                    out.append(' ' * indent + '"droppable_only": True,')
            if depth == 0:
                cur_key = None
        out.append(line)

    src = '\n'.join(out)

    # ── Pass 5: Rewrite get_caravan_stock() ──────────────────────────────────
    src = re.sub(
        r'def get_caravan_stock\(\):.*?(?=\n(?:HEMLOCK_STOCK|ALIASES|\Z))',
        NEW_CARAVAN_FUNC + '\n',
        src,
        flags=re.DOTALL,
    )

    # ── Pass 6: Rewrite HEMLOCK_STOCK_* blocks ────────────────────────────────
    src = re.sub(
        r'HEMLOCK_STOCK_WEAPONS\s*=.*?HEMLOCK_STOCK_CONSUMABLES\s*=\s*\[.*?\]',
        NEW_HEMLOCK.rstrip(),
        src,
        flags=re.DOTALL,
    )

    return src


if __name__ == '__main__':
    src_path = sys.argv[1]
    dst_path = sys.argv[2] if len(sys.argv) > 2 else src_path
    with open(src_path, 'r', encoding='utf-8') as f:
        src = f.read()
    result = process(src)
    with open(dst_path, 'w', encoding='utf-8') as f:
        f.write(result)

    # Quick audit
    drop_count  = result.count('"droppable_only": True')
    price_hits  = sum(1 for k in PRICES if f'"value": {PRICES[k]}' in result)
    print(f"Done → {dst_path}")
    print(f"  droppable_only injected : {drop_count}")
    print(f"  price targets confirmed : {price_hits}/{len(PRICES)}")
