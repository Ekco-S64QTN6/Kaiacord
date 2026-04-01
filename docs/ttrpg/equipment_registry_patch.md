# equipment_registry.py — Patch Instructions

## Summary of Changes

### Strategy
- Move all class tag assignments **inline** into each item definition
- Remove the "Part 1" post-assignment block entirely
- Add advanced class tags (Paladin, Shadowknight, etc.) where thematically appropriate
- Clean up inconsistent formatting

---

## SECTION 1 — Fix inline class tags in existing WEAPONS

### ghoulbane
FIND:
    "ghoulbane":      {"name": "Ghoulbane",        "attack_bonus": 5, "damage_die": 8,  "damage_bonus": 4, "value": 180, "tier": 3, "classes": ["Warrior", "Cleric"]},

REPLACE WITH:
    "ghoulbane":      {"name": "Ghoulbane",        "attack_bonus": 5, "damage_die": 8,  "damage_bonus": 4, "value": 180, "tier": 3, "classes": ["Warrior", "Paladin", "Cleric"]},

### fiery_avenger
FIND:
    "fiery_avenger":  {"name": "Fiery Avenger",    "attack_bonus": 7, "damage_die": 10, "damage_bonus": 6, "value": 280, "tier": 4, "classes": ["Warrior"]},

REPLACE WITH:
    "fiery_avenger":  {"name": "Fiery Avenger",    "attack_bonus": 7, "damage_die": 10, "damage_bonus": 6, "value": 280, "tier": 4, "classes": ["Warrior", "Paladin"]},

### blood_sword
FIND:
    "blood_sword":    {"name": "Blood Sword",      "attack_bonus": 6, "damage_die": 8,  "damage_bonus": 6, "value": 200, "tier": 4},

REPLACE WITH:
    "blood_sword":    {"name": "Blood Sword",      "attack_bonus": 6, "damage_die": 8,  "damage_bonus": 6, "value": 200, "tier": 4, "classes": ["Warrior", "Shadowknight"]},

### sun_blade
FIND:
    "sun_blade":      {"name": "Sun Blade",        "attack_bonus": 8, "damage_die": 10, "damage_bonus": 6, "value": 450, "tier": 4},

REPLACE WITH:
    "sun_blade":      {"name": "Sun Blade",        "attack_bonus": 8, "damage_die": 10, "damage_bonus": 6, "value": 450, "tier": 4, "classes": ["Warrior", "Paladin"]},

### resonance_staff
FIND:
    "resonance_staff": {"name": "Resonance Staff", "attack_bonus": 5, "damage_die": 10, "damage_bonus": 6, "value": 180, "tier": 4, "classes": ["Mage", "Cleric"]},

REPLACE WITH:
    "resonance_staff": {"name": "Resonance Staff", "attack_bonus": 5, "damage_die": 10, "damage_bonus": 6, "value": 180, "tier": 4, "classes": ["Mage", "Cleric", "Wizard", "Necromancer"]},

### resonance_bow
FIND:
    "resonance_bow":  {"name": "Resonance Bow",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 200, "tier": 4},

REPLACE WITH:
    "resonance_bow":  {"name": "Resonance Bow",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 200, "tier": 4, "classes": ["Ranger", "Hunter"]},

### yoichi_bow (already has Ranger, add Hunter)
FIND:
    "yoichi_bow":     {"name": "Yoichi Bow",       "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 250, "tier": 4, "classes": ["Ranger"]},

REPLACE WITH:
    "yoichi_bow":     {"name": "Yoichi Bow",       "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 250, "tier": 4, "classes": ["Ranger", "Hunter"]},

### disruption_mace
FIND:
    "disruption_mace":{"name": "Mace of Disruption","attack_bonus": 6, "damage_die": 8,  "damage_bonus": 6, "value": 300, "tier": 4, "classes": ["Cleric"]},

REPLACE WITH:
    "disruption_mace":{"name": "Mace of Disruption","attack_bonus": 6, "damage_die": 8,  "damage_bonus": 6, "value": 300, "tier": 4, "classes": ["Cleric", "Paladin", "High Priest"]},

### void_blade (Tier 5)
FIND:
    "void_blade":     {"name": "Void Blade",       "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 500, "tier": 5},

REPLACE WITH:
    "void_blade":     {"name": "Void Blade",       "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 500, "tier": 5, "classes": ["Warrior", "Shadowknight", "Shadowblade"]},

### holy_avenger
FIND:
    "holy_avenger":   {"name": "Holy Avenger",     "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 600, "tier": 5, "classes": ["Warrior", "Cleric"]},

REPLACE WITH:
    "holy_avenger":   {"name": "Holy Avenger",     "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 600, "tier": 5, "classes": ["Warrior", "Paladin"]},

### vorpal_sword
FIND:
    "vorpal_sword":   {"name": "Vorpal Sword",     "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 750, "tier": 5, "classes": ["Warrior", "Rogue"]},

REPLACE WITH:
    "vorpal_sword":   {"name": "Vorpal Sword",     "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 750, "tier": 5, "classes": ["Warrior", "Rogue", "Shadowblade"]},

### staff_magi
FIND:
    "staff_magi":     {"name": "Staff of the Magi","attack_bonus": 8, "damage_die": 10, "damage_bonus": 8, "value": 650, "tier": 5, "classes": ["Mage"]},

REPLACE WITH:
    "staff_magi":     {"name": "Staff of the Magi","attack_bonus": 8, "damage_die": 10, "damage_bonus": 8, "value": 650, "tier": 5, "classes": ["Mage", "Wizard", "Necromancer"]},

### soulfire
FIND:
    "soulfire":       {"name": "Soulfire",         "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 700, "tier": 5, "classes": ["Cleric"]},

REPLACE WITH:
    "soulfire":       {"name": "Soulfire",         "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 700, "tier": 5, "classes": ["Cleric", "Paladin", "High Priest"]},

### excalibur_ff
FIND:
    "excalibur_ff":   {"name": "Excalibur",        "attack_bonus": 11,"damage_die": 12, "damage_bonus": 8, "value": 900, "tier": 5, "classes": ["Warrior"]},

REPLACE WITH:
    "excalibur_ff":   {"name": "Excalibur",        "attack_bonus": 11,"damage_die": 12, "damage_bonus": 8, "value": 900, "tier": 5, "classes": ["Warrior", "Paladin"]},

### ragnarok_ff
FIND:
    "ragnarok_ff":    {"name": "Ragnarok",         "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 850, "tier": 5, "classes": ["Warrior"]},

REPLACE WITH:
    "ragnarok_ff":    {"name": "Ragnarok",         "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 850, "tier": 5, "classes": ["Warrior", "Shadowknight"]},

### masamune
FIND:
    "masamune":       {"name": "Masamune",         "attack_bonus": 8, "damage_die": 12, "damage_bonus": 6, "value": 400, "tier": 4, "classes": ["Warrior", "Rogue"]},

REPLACE WITH:
    "masamune":       {"name": "Masamune",         "attack_bonus": 8, "damage_die": 12, "damage_bonus": 6, "value": 400, "tier": 4, "classes": ["Warrior", "Rogue", "Shadowblade"]},

### mjolnir
FIND:
    "mjolnir":        {"name": "Mjolnir",          "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 680, "tier": 5, "classes": ["Warrior", "Cleric"]},

REPLACE WITH:
    "mjolnir":        {"name": "Mjolnir",          "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 680, "tier": 5, "classes": ["Warrior", "Paladin", "Cleric"]},

### shining_staff
FIND:
    "shining_staff":  {"name": "Shining Staff",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 220, "tier": 4, "classes": ["Mage", "Cleric"]},

REPLACE WITH:
    "shining_staff":  {"name": "Shining Staff",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 220, "tier": 4, "classes": ["Mage", "Cleric", "Wizard", "High Priest"]},

### aeridorian_axe (Warrior only is fine, but could also be open)
(leave as is)

---

## SECTION 2 — Fix inline class tags in existing ARMOR

### bronze_armor
FIND:
    "bronze_armor":     {"name": "Bronze Armor",      "defense_bonus": 3, "value": 30,  "tier": 1},

REPLACE WITH:
    "bronze_armor":     {"name": "Bronze Armor",      "defense_bonus": 3, "value": 30,  "tier": 1, "classes": ["Warrior", "Ranger"]},

### studded_leather
FIND:
    "studded_leather":  {"name": "Studded Leather",   "defense_bonus": 3, "value": 40,  "tier": 2},

REPLACE WITH:
    "studded_leather":  {"name": "Studded Leather",   "defense_bonus": 3, "value": 40,  "tier": 2, "classes": ["Warrior", "Ranger", "Rogue"]},

### chainmail
FIND:
    "chainmail":        {"name": "Chainmail",          "defense_bonus": 5, "value": 80,  "tier": 2},

REPLACE WITH:
    "chainmail":        {"name": "Chainmail",          "defense_bonus": 5, "value": 80,  "tier": 2, "classes": ["Warrior", "Ranger", "Cleric"]},

### half_plate
FIND:
    "half_plate":       {"name": "Half Plate",         "defense_bonus": 7, "value": 150, "tier": 3},

REPLACE WITH:
    "half_plate":       {"name": "Half Plate",         "defense_bonus": 7, "value": 150, "tier": 3, "classes": ["Warrior", "Paladin"]},

### flame_mail
FIND:
    "flame_mail":       {"name": "Flame Mail",        "defense_bonus": 7, "value": 160, "tier": 3},

REPLACE WITH:
    "flame_mail":       {"name": "Flame Mail",        "defense_bonus": 7, "value": 160, "tier": 3, "classes": ["Warrior"]},

### ice_armor
FIND:
    "ice_armor":        {"name": "Ice Armor",         "defense_bonus": 7, "value": 160, "tier": 3},

REPLACE WITH:
    "ice_armor":        {"name": "Ice Armor",         "defense_bonus": 7, "value": 160, "tier": 3, "classes": ["Warrior"]},

### mithral_shirt
FIND:
    "mithral_shirt":    {"name": "Mithral Chain Shirt","defense_bonus": 6, "value": 250, "tier": 3},

REPLACE WITH:
    "mithral_shirt":    {"name": "Mithral Chain Shirt","defense_bonus": 6, "value": 250, "tier": 3, "classes": ["Warrior", "Ranger", "Rogue"]},

### full_plate
FIND:
    "full_plate":       {"name": "Full Plate",         "defense_bonus": 9, "value": 300, "tier": 4},

REPLACE WITH:
    "full_plate":       {"name": "Full Plate",         "defense_bonus": 9, "value": 300, "tier": 4, "classes": ["Warrior", "Paladin"]},

### diamond_armor
FIND:
    "diamond_armor":    {"name": "Diamond Armor",     "defense_bonus": 8, "value": 220, "tier": 4},

REPLACE WITH:
    "diamond_armor":    {"name": "Diamond Armor",     "defense_bonus": 8, "value": 220, "tier": 4, "classes": ["Warrior"]},

### fur_cloak (no restriction needed — it's a cosmetic cloak, anyone can wear it)
(leave as is — it's a general item Hemlock sells in winter)

---

## SECTION 3 — Delete the "Part 1" block entirely

FIND AND DELETE this entire block (starts around line "# Part 1 — Fix missing class tags on existing items"):

```python
# Part 1 — Fix missing class tags on existing items
WEAPONS["shortbow"]["classes"] = ["Ranger", "Rogue"]
WEAPONS["crossbow"]["classes"] = ["Ranger", "Rogue"]
WEAPONS["iron_dirk"]["classes"] = ["Rogue", "Ranger"]
WEAPONS["iron_spear"]["classes"] = ["Warrior", "Ranger"]
WEAPONS["iron_battle_axe"]["classes"] = ["Warrior"]
WEAPONS["steel_longsword"]["classes"] = ["Warrior", "Ranger"]
WEAPONS["flame_sword"]["classes"] = ["Warrior"]
WEAPONS["ice_brand"]["classes"] = ["Warrior"]
WEAPONS["sun_blade"]["classes"] = ["Warrior", "Paladin"]
WEAPONS["blood_sword"]["classes"] = ["Warrior", "Rogue", "Shadowknight"]
WEAPONS["void_blade"]["classes"] = ["Warrior", "Rogue", "Shadowblade"]
WEAPONS["vorpal_sword"]["classes"] = ["Warrior", "Rogue"]

ARMOR["bronze_armor"]["classes"] = ["Warrior", "Ranger"]
ARMOR["studded_leather"]["classes"] = ["Warrior", "Ranger", "Rogue"]
ARMOR["chainmail"]["classes"] = ["Warrior", "Ranger", "Cleric"]
ARMOR["half_plate"]["classes"] = ["Warrior", "Paladin"]
ARMOR["full_plate"]["classes"] = ["Warrior", "Paladin"]
ARMOR["diamond_armor"]["classes"] = ["Warrior"]
ARMOR["flame_mail"]["classes"] = ["Warrior"]
ARMOR["ice_armor"]["classes"] = ["Warrior"]
ARMOR["mithral_shirt"]["classes"] = ["Warrior", "Ranger", "Rogue"]
ARMOR["fur_cloak"]["classes"] = ["Warrior", "Ranger", "Rogue"]
```

REPLACE WITH nothing (delete it).

---

## SECTION 4 — Inline fixes for new Warrior weapons (already in new section, confirm these are correct)

In the new Warrior weapons section, update these that should also allow Paladin:

### aeridorian_greatsword
FIND:
    "aeridorian_greatsword": {
        "name": "Aeridorian Greatsword", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 300, "tier": 4,
        "classes": ["Warrior"],
    },

REPLACE WITH:
    "aeridorian_greatsword": {
        "name": "Aeridorian Greatsword", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 300, "tier": 4,
        "classes": ["Warrior", "Paladin"],
    },

### champions_legacy
FIND:
    "champions_legacy": {
        "name": "Champion's Legacy", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 600, "tier": 5,
        "classes": ["Warrior"],
    },

REPLACE WITH:
    "champions_legacy": {
        "name": "Champion's Legacy", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 600, "tier": 5,
        "classes": ["Warrior", "Paladin"],
    },

---

## SECTION 5 — Inline fixes for new Rogue weapons (Shadowblade should also use these)

### the_quiet_death
FIND:
    "the_quiet_death": {
        "name": "The Quiet Death", "attack_bonus": 7, "damage_die": 10,
        "damage_bonus": 6, "value": 265, "tier": 4,
        "classes": ["Rogue"],
    },

REPLACE WITH:
    "the_quiet_death": {
        "name": "The Quiet Death", "attack_bonus": 7, "damage_die": 10,
        "damage_bonus": 6, "value": 265, "tier": 4,
        "classes": ["Rogue", "Shadowblade"],
    },

### voidstep_blade
FIND:
    "voidstep_blade": {
        "name": "Voidstep Blade", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 730, "tier": 5,
        "classes": ["Rogue"],
    },

REPLACE WITH:
    "voidstep_blade": {
        "name": "Voidstep Blade", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 730, "tier": 5,
        "classes": ["Rogue", "Shadowblade"],
    },

### the_last_laugh
FIND:
    "the_last_laugh": {
        "name": "The Last Laugh", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 610, "tier": 5,
        "classes": ["Rogue"],
    },

REPLACE WITH:
    "the_last_laugh": {
        "name": "The Last Laugh", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 610, "tier": 5,
        "classes": ["Rogue", "Trickster"],
    },

---

## SECTION 6 — Mage weapons: add Wizard/Necromancer tags

### null_scepter
FIND:
    "null_scepter": {
        "name": "Null Scepter", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 690, "tier": 5,
        "classes": ["Mage"],
    },

REPLACE WITH:
    "null_scepter": {
        "name": "Null Scepter", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 690, "tier": 5,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },

### the_whispering_wand
FIND:
    "the_whispering_wand": {
        "name": "The Whispering Wand", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 270, "tier": 4,
        "classes": ["Mage"],
    },

REPLACE WITH:
    "the_whispering_wand": {
        "name": "The Whispering Wand", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 270, "tier": 4,
        "classes": ["Mage", "Wizard"],
    },

### void_orb (Necromancer especially, also Wizard)
FIND:
    "void_orb": {
        "name": "Void Orb", "attack_bonus": 6, "damage_die": 12,
        "damage_bonus": 6, "value": 225, "tier": 4,
        "classes": ["Mage"],
    },

REPLACE WITH:
    "void_orb": {
        "name": "Void Orb", "attack_bonus": 6, "damage_die": 12,
        "damage_bonus": 6, "value": 225, "tier": 4,
        "classes": ["Mage", "Necromancer"],
    },

---

## SECTION 7 — Cleric weapons: add High Priest/Paladin/Shaman tags

### morvenna_flail
FIND:
    "morvenna_flail": {
        "name": "Morvenna's Flail", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 615, "tier": 5,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "morvenna_flail": {
        "name": "Morvenna's Flail", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 615, "tier": 5,
        "classes": ["Cleric", "Shadowknight", "High Priest"],
    },

### voice_of_dawn
FIND:
    "voice_of_dawn": {
        "name": "Voice of Dawn", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 760, "tier": 5,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "voice_of_dawn": {
        "name": "Voice of Dawn", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 760, "tier": 5,
        "classes": ["Cleric", "Paladin", "High Priest"],
    },

### dawn_hammer
FIND:
    "dawn_hammer": {
        "name": "Dawn Hammer", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 275, "tier": 4,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "dawn_hammer": {
        "name": "Dawn Hammer", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 275, "tier": 4,
        "classes": ["Cleric", "Paladin", "High Priest"],
    },

---

## SECTION 8 — Ranger weapons: add Hunter tag to new items

### moonbow
FIND:
    "moonbow": {
        "name": "Moonbow", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 285, "tier": 4,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "moonbow": {
        "name": "Moonbow", "attack_bonus": 7, "damage_die": 12,
        "damage_bonus": 6, "value": 285, "tier": 4,
        "classes": ["Ranger", "Hunter"],
    },

### silent_stalker_bow
FIND:
    "silent_stalker_bow": {
        "name": "Silent Stalker Bow", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 650, "tier": 5,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "silent_stalker_bow": {
        "name": "Silent Stalker Bow", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 650, "tier": 5,
        "classes": ["Ranger", "Hunter"],
    },

### aeridor_longbow
FIND:
    "aeridor_longbow": {
        "name": "Aeridor Longbow", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 235, "tier": 4,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "aeridor_longbow": {
        "name": "Aeridor Longbow", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 235, "tier": 4,
        "classes": ["Ranger", "Hunter"],
    },

---

## SECTION 9 — Ranger armor: add Warden where appropriate

### whisperwood_garb
FIND:
    "whisperwood_garb": {
        "name": "Whisperwood Garb", "defense_bonus": 6, "value": 145, "tier": 3,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "whisperwood_garb": {
        "name": "Whisperwood Garb", "defense_bonus": 6, "value": 145, "tier": 3,
        "classes": ["Ranger", "Warden"],
    },

### forest_sovereign_armor
FIND:
    "forest_sovereign_armor": {
        "name": "Forest Sovereign Armor", "defense_bonus": 11, "value": 685, "tier": 5,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "forest_sovereign_armor": {
        "name": "Forest Sovereign Armor", "defense_bonus": 11, "value": 685, "tier": 5,
        "classes": ["Ranger", "Warden"],
    },

### ghost_leather
FIND:
    "ghost_leather": {
        "name": "Ghost Leather", "defense_bonus": 9, "value": 295, "tier": 4,
        "classes": ["Ranger"],
    },

REPLACE WITH:
    "ghost_leather": {
        "name": "Ghost Leather", "defense_bonus": 9, "value": 295, "tier": 4,
        "classes": ["Ranger", "Hunter", "Warden"],
    },

---

## SECTION 10 — Rogue armor: add Shadowblade/Trickster

### void_cloth
FIND:
    "void_cloth": {
        "name": "Void Cloth", "defense_bonus": 9, "value": 290, "tier": 4,
        "classes": ["Rogue"],
    },

REPLACE WITH:
    "void_cloth": {
        "name": "Void Cloth", "defense_bonus": 9, "value": 290, "tier": 4,
        "classes": ["Rogue", "Shadowblade"],
    },

### void_mantle
FIND:
    "void_mantle": {
        "name": "Void Mantle", "defense_bonus": 11, "value": 665, "tier": 5,
        "classes": ["Rogue"],
    },

REPLACE WITH:
    "void_mantle": {
        "name": "Void Mantle", "defense_bonus": 11, "value": 665, "tier": 5,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

---

## SECTION 11 — Mage armor: add Wizard/Necromancer

### void_vestment
FIND:
    "void_vestment": {
        "name": "Void Vestment", "defense_bonus": 8, "value": 305, "tier": 4,
        "classes": ["Mage"],
    },

REPLACE WITH:
    "void_vestment": {
        "name": "Void Vestment", "defense_bonus": 8, "value": 305, "tier": 4,
        "classes": ["Mage", "Necromancer"],
    },

### arcanist_shroud
FIND:
    "arcanist_shroud": {
        "name": "Arcanist's Shroud", "defense_bonus": 10, "value": 630, "tier": 5,
        "classes": ["Mage"],
    },

REPLACE WITH:
    "arcanist_shroud": {
        "name": "Arcanist's Shroud", "defense_bonus": 10, "value": 630, "tier": 5,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },

---

## SECTION 12 — Cleric armor: add Paladin/High Priest/Shaman

### saint_plate
FIND:
    "saint_plate": {
        "name": "Saint's Plate", "defense_bonus": 10, "value": 340, "tier": 4,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "saint_plate": {
        "name": "Saint's Plate", "defense_bonus": 10, "value": 340, "tier": 4,
        "classes": ["Cleric", "Paladin", "High Priest"],
    },

### voice_of_silence_armor
FIND:
    "voice_of_silence_armor": {
        "name": "Voice of Silence Armor", "defense_bonus": 11, "value": 730, "tier": 5,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "voice_of_silence_armor": {
        "name": "Voice of Silence Armor", "defense_bonus": 11, "value": 730, "tier": 5,
        "classes": ["Cleric", "Paladin", "High Priest", "Shaman"],
    },

### cleric_plate
FIND:
    "cleric_plate": {
        "name": "Cleric's Plate", "defense_bonus": 7, "value": 152, "tier": 3,
        "classes": ["Cleric"],
    },

REPLACE WITH:
    "cleric_plate": {
        "name": "Cleric's Plate", "defense_bonus": 7, "value": 152, "tier": 3,
        "classes": ["Cleric", "Paladin"],
    },

### shrine_chainmail
FIND:
    "shrine_chainmail": {
        "name": "Shrine Chainmail", "defense_bonus": 5, "value": 70, "tier": 2,
        "classes": ["Cleric", "Warrior"],
    },

REPLACE WITH:
    "shrine_chainmail": {
        "name": "Shrine Chainmail", "defense_bonus": 5, "value": 70, "tier": 2,
        "classes": ["Cleric", "Warrior", "Paladin"],
    },

---

## SECTION 13 — Accessories for advanced classes

### silence_sigil (already Cleric — add High Priest)
FIND:
    "silence_sigil": {
        "name": "Silence Sigil", "defense_bonus": 2, "attack_bonus": 2,
        "value": 510, "tier": 5, "classes": ["Cleric"],
    },

REPLACE WITH:
    "silence_sigil": {
        "name": "Silence Sigil", "defense_bonus": 2, "attack_bonus": 2,
        "value": 510, "tier": 5, "classes": ["Cleric", "High Priest", "Shaman"],
    },

### void_focus
FIND:
    "void_focus": {
        "name": "Void Focus", "defense_bonus": 1, "attack_bonus": 3,
        "value": 210, "tier": 4, "classes": ["Mage"],
    },

REPLACE WITH:
    "void_focus": {
        "name": "Void Focus", "defense_bonus": 1, "attack_bonus": 3,
        "value": 210, "tier": 4, "classes": ["Mage", "Wizard", "Necromancer"],
    },

### void_ring
FIND:
    "void_ring": {
        "name": "Void Ring", "defense_bonus": 1, "attack_bonus": 3,
        "value": 198, "tier": 4, "classes": ["Rogue"],
    },

REPLACE WITH:
    "void_ring": {
        "name": "Void Ring", "defense_bonus": 1, "attack_bonus": 3,
        "value": 198, "tier": 4, "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

---

## Full class tag philosophy (for reference)

| Advanced Class  | Can use gear from     | Notes                                    |
|-----------------|-----------------------|------------------------------------------|
| Paladin         | Warrior, Cleric       | Holy warrior — plate + holy weapons     |
| Shadowknight    | Warrior               | Dark plate + cursed/dark weapons         |
| Hunter          | Ranger                | All Ranger gear + bow-specialist items  |
| Warden          | Ranger                | Forest-themed Ranger gear               |
| Wizard          | Mage                  | INT-specialist Mage gear                |
| Necromancer     | Mage                  | Dark/void Mage gear                     |
| Shadowblade     | Rogue                 | High-end Rogue + void weapons           |
| Trickster       | Rogue                 | Rogue gear, no special expansions       |
| High Priest     | Cleric                | Top-tier Cleric gear                    |
| Shaman          | Cleric                | Nature-adjacent Cleric gear             |

**Key rule:** Advanced classes can use all base class gear. Only special/thematic items
restrict to advanced class. The `classes` array in equipment_registry must include
BOTH the base class string AND the advanced class string for the engine to accept it
(since `sheet["class"]` stores the base class, `sheet["advanced_class"]` stores the
advanced class, and `_handle_equip` checks `item_classes` vs `sheet.get("class")`).

⚠️  IMPORTANT: Check `_handle_equip` in rpg_handler.py — it currently only checks
`sheet.get("class")`, not `sheet.get("advanced_class")`. The fix:

```python
# In _handle_equip, replace:
if item_classes and sheet.get("class") not in item_classes:

# With:
char_class = sheet.get("class", "")
adv_class  = sheet.get("advanced_class", "")
if item_classes and char_class not in item_classes and adv_class not in item_classes:
```

This one-line change is REQUIRED for advanced class items to equip correctly.
