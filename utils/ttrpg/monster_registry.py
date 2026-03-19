"""
monster_registry.py — Aethelgard Bestiary
==========================================
~120 monsters across 6 tiers, heavily inspired by Final Fantasy V.
ADAPTED to Aethelgard's lore: Whisperwood, Aeridor ruins, trade road, etc.

Stat guide:
  hp       — hit points
  attack   — flat bonus added to damage roll (1d6 + attack // 2)
  defense  — AC equivalent; player must beat this to land a hit
  xp       — awarded on defeat (split among party)
  gil      — gold dropped
  tier     — trivial / easy / medium / hard / deadly / boss
  desc     — fed to Kaia for narration flavor

Defense formula reference:
  Player effective DEF = 10 + DEX mod + armor bonus
  So DEF 8 = most players hit easily. DEF 18 = only strong builds connect.
"""



MONSTERS = {

    # ══════════════════════════════════════════════════════
    # TIER: TRIVIAL  (Level 1-2)
    # ══════════════════════════════════════════════════════

    "goblin": {
        "name": "Goblin",
        "hp": 16, "attack": 3, "defense": 8,
        "xp": 25, "gil": 6, "tier": "trivial",
        "desc": "A scrappy green-skinned scavenger armed with a chipped blade. Bold in numbers, cowardly alone.",
    },
    "goblin_guard": {
        "name": "Goblin Guard",
        "hp": 22, "attack": 4, "defense": 9,
        "xp": 30, "gil": 8, "tier": "trivial",
        "desc": "A goblin that found a dented shield somewhere. It's more annoying than dangerous.",
    },
    "bat": {
        "name": "Vampire Bat",
        "hp": 10, "attack": 4, "defense": 10,
        "xp": 20, "gil": 3, "tier": "trivial",
        "desc": "A blood-draining cave bat. Evasive and quick. Fragile if you can hit it.",
    },
    "flan": {
        "name": "Flan",
        "hp": 20, "attack": 2, "defense": 7,
        "xp": 20, "gil": 5, "tier": "trivial",
        "desc": "A gelatinous pudding creature. Slow and dim. Blunt weapons bounce off it uselessly.",
    },
    "black_flan": {
        "name": "Black Flan",
        "hp": 24, "attack": 3, "defense": 8,
        "xp": 25, "gil": 6, "tier": "trivial",
        "desc": "A darker, denser variant of the common flan. Leaves a staining residue on anything it touches.",
    },
    "moldwynd": {
        "name": "Moldwynd",
        "hp": 12, "attack": 3, "defense": 9,
        "xp": 18, "gil": 4, "tier": "trivial",
        "desc": "A wisp of wind and spore. It doesn't so much attack as drift into you at speed.",
    },
    "elf_toad": {
        "name": "Elf Toad",
        "hp": 14, "attack": 2, "defense": 8,
        "xp": 15, "gil": 3, "tier": "trivial",
        "desc": "An oversized toad with faintly luminescent skin. Its croak is disorienting at close range.",
    },
    "killer_bee": {
        "name": "Killer Bee",
        "hp": 8, "attack": 5, "defense": 11,
        "xp": 20, "gil": 2, "tier": "trivial",
        "desc": "Fast, venomous, and small enough to be maddening. Usually comes in groups.",
    },
    "microchu": {
        "name": "Microchu",
        "hp": 10, "attack": 3, "defense": 9,
        "xp": 22, "gil": 4, "tier": "trivial",
        "desc": "A tiny cactus creature that peppers you with needle-fine spines and then scurries off.",
    },
    "sahagin": {
        "name": "Sahagin",
        "hp": 18, "attack": 4, "defense": 9,
        "xp": 28, "gil": 7, "tier": "trivial",
        "desc": "A fish-man that haunts the Tricklebrook and the soggy edges of the Whisperwood. Smells terrible.",
    },
    "stroper": {
        "name": "Stroper",
        "hp": 15, "attack": 5, "defense": 10,
        "xp": 25, "gil": 5, "tier": "trivial",
        "desc": "A many-limbed thing that clings to cave ceilings. Drops on you when you walk underneath.",
    },
    "blood_slime": {
        "name": "Blood Slime",
        "hp": 18, "attack": 3, "defense": 7,
        "xp": 20, "gil": 4, "tier": "trivial",
        "desc": "A crimson ooze that seeps under doors and through cracks. It digests things slowly and completely.",
    },
    "crew_dust": {
        "name": "Crew Dust",
        "hp": 12, "attack": 4, "defense": 10,
        "xp": 18, "gil": 3, "tier": "trivial",
        "desc": "A floating cloud of animate ash, remnant of something burned long ago.",
    },

    # ── Additional TRIVIAL (early game variety) ────────────────────────────────

    "grat": {
        "name": "Grat",
        "hp": 14, "attack": 3, "defense": 8,
        "xp": 18, "gil": 4, "tier": "trivial",
        "desc": "A tentacled plant creature that roots itself near water and grabs passing legs.",
    },
    "nutkin": {
        "name": "Nutkin",
        "hp": 8, "attack": 2, "defense": 8,
        "xp": 12, "gil": 2, "tier": "trivial",
        "desc": "An oversized squirrel with a mean disposition and a habit of hoarding sharp things.",
    },
    "forest_boar": {
        "name": "Forest Boar",
        "hp": 22, "attack": 4, "defense": 8,
        "xp": 24, "gil": 8, "tier": "trivial",
        "desc": "A tusked pig that charges when startled. Startles easily.",
    },
    "snipper": {
        "name": "Snipper",
        "hp": 18, "attack": 4, "defense": 10,
        "xp": 22, "gil": 6, "tier": "trivial",
        "desc": "A large crab that wandered far from any water. Confused and aggressive.",
    },
    "myconid": {
        "name": "Myconid",
        "hp": 16, "attack": 3, "defense": 8,
        "xp": 20, "gil": 5, "tier": "trivial",
        "desc": "A walking mushroom creature that releases confusion spores when struck.",
    },
    "mud_flan": {
        "name": "Mud Flan",
        "hp": 24, "attack": 2, "defense": 7,
        "xp": 22, "gil": 5, "tier": "trivial",
        "desc": "A flan variant made of mud rather than gelatine. Slower, dirtier, equally unpleasant.",
    },
    "leaf_bunny": {
        "name": "Leaf Bunny",
        "hp": 6, "attack": 3, "defense": 11,
        "xp": 15, "gil": 3, "tier": "trivial",
        "desc": "A small creature that looks harmless. Bites hard and bolts. Usually gone before you can react.",
    },
    "thorn_lizard": {
        "name": "Thorn Lizard",
        "hp": 16, "attack": 4, "defense": 10,
        "xp": 22, "gil": 4, "tier": "trivial",
        "desc": "A relative of the lizardman that never outgrew its spikes. Hard to grab.",
    },
    "snow_bunny": {
        "name": "Snow Bunny",
        "hp": 6, "attack": 2, "defense": 12,
        "xp": 15, "gil": 4, "tier": "trivial",
        "desc": "A white rabbit with eyes like chips of ice. Incredibly fast. Bites when cornered. Winter only.",
    },
    "ice_wisp": {
        "name": "Ice Wisp",
        "hp": 8, "attack": 5, "defense": 13,
        "xp": 22, "gil": 0, "tier": "trivial",
        "desc": "A floating light that appears on frozen nights. Cold radiates from it. Drops nothing.",
    },
    "bloom_creeper": {
        "name": "Bloom Creeper",
        "hp": 18, "attack": 5, "defense": 8,
        "xp": 28, "gil": 5, "tier": "trivial",
        "desc": "A vine creature that only mobilizes in spring when new growth gives it reach. Smells like flowers. Strangles things.",
    },
    "summer_hornet": {
        "name": "Summer Hornet",
        "hp": 9, "attack": 6, "defense": 12,
        "xp": 25, "gil": 2, "tier": "trivial",
        "desc": "A hornet the size of a fist. Summer heat makes them aggressive. Nests near the Whisperwood edge in July and August.",
    },
    "wisp": {
        "name": "Will-o'-Wisp",
        "hp": 10, "attack": 4, "defense": 12,
        "xp": 22, "gil": 0, "tier": "trivial",
        "desc": "A floating light. It draws you off the path and then attacks. Classic. Drops nothing.",
    },
    "shadow_hound": {
        "name": "Shadow Hound",
        "hp": 20, "attack": 5, "defense": 10,
        "xp": 28, "gil": 6, "tier": "trivial",
        "desc": "A dog-shaped shadow that has developed opinions about territory.",
    },

    # ══════════════════════════════════════════════════════
    # TIER: EASY  (Level 2-4)
    # ══════════════════════════════════════════════════════

    "skeleton": {
        "name": "Skeleton",
        "hp": 30, "attack": 5, "defense": 10,
        "xp": 45, "gil": 8, "tier": "easy",
        "desc": "Animated bone. Slow, relentless. Takes reduced damage from slashing weapons. Fire works.",
    },
    "zombie": {
        "name": "Zombie",
        "hp": 42, "attack": 5, "defense": 8,
        "xp": 40, "gil": 5, "tier": "easy",
        "desc": "A shambling corpse. Nearly unstoppable through attrition alone. Burns well.",
    },
    "ghoul": {
        "name": "Ghoul",
        "hp": 35, "attack": 6, "defense": 10,
        "xp": 50, "gil": 10, "tier": "easy",
        "desc": "A grave-robber's nightmare. Fast for undead, and it remembers how to use its hands.",
    },
    "wolf": {
        "name": "Dire Wolf",
        "hp": 28, "attack": 6, "defense": 10,
        "xp": 45, "gil": 8, "tier": "easy",
        "desc": "A large ash-grey wolf with black eyes. Hunts in packs. Faster than it looks.",
    },
    "ghost": {
        "name": "Ghost",
        "hp": 20, "attack": 7, "defense": 13,
        "xp": 55, "gil": 0, "tier": "easy",
        "desc": "A flickering translucent figure. Hard to hit. Cold radiates outward from it. Drops nothing.",
    },
    "black_goblin": {
        "name": "Black Goblin",
        "hp": 30, "attack": 6, "defense": 10,
        "xp": 48, "gil": 10, "tier": "easy",
        "desc": "A smarter, meaner cousin of the common goblin. Carries poison on its blade.",
    },
    "cockatrice": {
        "name": "Cockatrice",
        "hp": 25, "attack": 5, "defense": 11,
        "xp": 52, "gil": 12, "tier": "easy",
        "desc": "A two-legged bird with a snake's tail and a petrifying gaze. Keep your eyes down.",
    },
    "steel_bat": {
        "name": "Steel Bat",
        "hp": 22, "attack": 7, "defense": 12,
        "xp": 50, "gil": 5, "tier": "easy",
        "desc": "A bat with hide like hammered iron. Its wing-buffets hit harder than they should.",
    },
    "gigas": {
        "name": "Gigas",
        "hp": 50, "attack": 7, "defense": 10,
        "xp": 60, "gil": 15, "tier": "easy",
        "desc": "A dim-witted giant barely taller than a man. More momentum than malice.",
    },
    "lizardman": {
        "name": "Lizardman",
        "hp": 38, "attack": 6, "defense": 11,
        "xp": 55, "gil": 12, "tier": "easy",
        "desc": "An armored reptilian warrior. Disciplined, moves in squads, fights without ego.",
    },
    "harpy": {
        "name": "Harpy",
        "hp": 30, "attack": 8, "defense": 12,
        "xp": 60, "gil": 10, "tier": "easy",
        "desc": "A winged woman with talons. Attacks from above, retreats before you close distance.",
    },
    "pink_puff": {
        "name": "Pink Puff",
        "hp": 20, "attack": 4, "defense": 12,
        "xp": 65, "gil": 50, "tier": "easy",   # high gil — rare drop
        "desc": "A rosy floating creature that looks harmless. It's mostly harmless. But it's full of gil for some reason.",
    },
    "moth": {
        "name": "Skull Eater",
        "hp": 5, "attack": 8, "defense": 14,
        "xp": 70, "gil": 30, "tier": "easy",   # very hard to hit, worth it
        "desc": "Tiny, incredibly fast, and vicious. Almost impossible to hit. If you manage it, it was worth it.",
    },
    "sea_snake": {
        "name": "Sea Snake",
        "hp": 32, "attack": 7, "defense": 10,
        "xp": 50, "gil": 9, "tier": "easy",
        "desc": "Found near the Tricklebrook and any standing water. Faster in mud than you'd expect.",
    },
    "bandit": {
        "name": "Road Bandit",
        "hp": 35, "attack": 7, "defense": 11,
        "xp": 55, "gil": 20, "tier": "easy",
        "desc": "A desperate man with a blade. The trade road made him this way. He's made his choice.",
    },
    "frost_wolf": {
        "name": "Frost Wolf",
        "hp": 32, "attack": 7, "defense": 11,
        "xp": 50, "gil": 10, "tier": "easy",
        "desc": "A pale grey wolf with ice-rimed fur. Hunts alone in winter when the pack disperses. Faster than its summer cousin.",
    },
    "snow_bandit": {
        "name": "Desperate Bandit",
        "hp": 30, "attack": 8, "defense": 10,
        "xp": 52, "gil": 18, "tier": "easy",
        "desc": "A road bandit in winter furs. Hungrier and less careful than his summer counterpart. Will fight harder.",
    },
    "antler_stag": {
        "name": "Antler Stag",
        "hp": 35, "attack": 6, "defense": 9,
        "xp": 45, "gil": 12, "tier": "easy",
        "desc": "An enormous stag driven to the forest edge by autumn hunger. Antlers like branches. Not aggressive — until it is.",
    },

    # ══════════════════════════════════════════════════════
    # TIER: MEDIUM  (Level 4-7)
    # ══════════════════════════════════════════════════════

    "gargoyle": {
        "name": "Gargoyle",
        "hp": 60, "attack": 9, "defense": 13,
        "xp": 90, "gil": 20, "tier": "medium",
        "desc": "Stone that moves. Aeridor ruins are full of them. They wait until you touch something.",
    },
    "ochu": {
        "name": "Ochu",
        "hp": 80, "attack": 8, "defense": 11,
        "xp": 100, "gil": 18, "tier": "medium",
        "desc": "A massive carnivorous plant with thrashing vine-arms. Its breath causes nausea at ten feet.",
    },
    "lamia": {
        "name": "Lamia",
        "hp": 65, "attack": 10, "defense": 13,
        "xp": 110, "gil": 30, "tier": "medium",
        "desc": "A serpent-woman. Her song carries across the Whisperwood. It makes you want to stand still.",
    },
    "golem": {
        "name": "Stone Golem",
        "hp": 100, "attack": 9, "defense": 15,
        "xp": 120, "gil": 0, "tier": "medium",
        "desc": "A construct of animated Aeridorian stone. Slow. Each step cracks the ground. Magic animates it.",
    },
    "dhorme_chimera": {
        "name": "Dhorme Chimera",
        "hp": 70, "attack": 11, "defense": 13,
        "xp": 115, "gil": 25, "tier": "medium",
        "desc": "A lion's body, goat head, serpent tail. Three creatures in one bad mood.",
    },
    "dark_wizard": {
        "name": "Dark Wizard",
        "hp": 55, "attack": 12, "defense": 11,
        "xp": 120, "gil": 35, "tier": "medium",
        "desc": "A robed figure with hands that emit cold light. Probably human once. Debatable now.",
    },
    "werewolf": {
        "name": "Werewolf",
        "hp": 75, "attack": 11, "defense": 12,
        "xp": 105, "gil": 15, "tier": "medium",
        "desc": "Not a monster by daylight. At night, something else entirely. The Whisperwood makes it worse.",
    },
    "wyvern": {
        "name": "Wyvern",
        "hp": 85, "attack": 11, "defense": 13,
        "xp": 115, "gil": 30, "tier": "medium",
        "desc": "A two-legged dragon. Breathes lightning. Territorial. Not fully grown. Worse when cornered.",
    },
    "abductor": {
        "name": "Abductor",
        "hp": 65, "attack": 10, "defense": 13,
        "xp": 100, "gil": 20, "tier": "medium",
        "desc": "A floating thing with too many eyes. It doesn't kill — it takes. Where it takes things is unclear.",
    },
    "soldier": {
        "name": "Aeridorian Soldier",
        "hp": 70, "attack": 10, "defense": 14,
        "xp": 110, "gil": 25, "tier": "medium",
        "desc": "A warrior animated by Aeridorian resonance. It still holds formation. It still remembers orders.",
    },
    "manticore": {
        "name": "Manticore",
        "hp": 90, "attack": 11, "defense": 13,
        "xp": 120, "gil": 28, "tier": "medium",
        "desc": "Lion body, human face, scorpion tail. It's smart enough to know it's terrifying.",
    },
    "cray_claw": {
        "name": "Cray Claw",
        "hp": 80, "attack": 9, "defense": 14,
        "xp": 105, "gil": 22, "tier": "medium",
        "desc": "An enormous crustacean that crawled up from underground. Its shell deflects most blades.",
    },
    "mini_satana": {
        "name": "Mini Satana",
        "hp": 60, "attack": 12, "defense": 12,
        "xp": 115, "gil": 30, "tier": "medium",
        "desc": "A small devil-creature. Not powerful. Very fast. Very loud. Calls things you don't want called.",
    },
    "magic_pot": {
        "name": "Magic Pot",
        "hp": 1, "attack": 1, "defense": 30,
        "xp": 200, "gil": 150, "tier": "medium",   # gimmick: almost invincible, huge reward
        "desc": "An animated pot that cannot be damaged by ordinary means. If you figure it out, you're rich.",
    },
    "reflect_mage": {
        "name": "Reflect Mage",
        "hp": 55, "attack": 11, "defense": 12,
        "xp": 110, "gil": 28, "tier": "medium",
        "desc": "A caster with a reflective field. Turns spells back on the caster. Physical attacks still work.",
    },
    "treant": {
        "name": "Treant",
        "hp": 110, "attack": 9, "defense": 13,
        "xp": 115, "gil": 10, "tier": "medium",
        "desc": "A walking tree. Patient beyond measure. It was here before the Whisperwood had a name.",
    },
    "wind_serpent": {
        "name": "Wind Serpent",
        "hp": 65, "attack": 12, "defense": 13,
        "xp": 110, "gil": 20, "tier": "medium",
        "desc": "A serpent that rides updrafts. It attacks on the dive, vanishing before you can swing back.",
    },
    "earth_bear": {
        "name": "Earth Bear",
        "hp": 100, "attack": 10, "defense": 12,
        "xp": 105, "gil": 15, "tier": "medium",
        "desc": "A massive brown bear with stone-encrusted paws. The Whisperwood deep produces them occasionally.",
    },
    "alchemist": {
        "name": "Rogue Alchemist",
        "hp": 50, "attack": 11, "defense": 11,
        "xp": 120, "gil": 45, "tier": "medium",
        "desc": "A former scholar who went too deep into the ruins. Throws volatile compounds. Unpredictable.",
    },

    # ══════════════════════════════════════════════════════
    # TIER: HARD  (Level 7-10)
    # ══════════════════════════════════════════════════════

    "tonberry": {
        "name": "Tonberry",
        "hp": 80, "attack": 22, "defense": 13,
        "xp": 220, "gil": 150, "tier": "hard",
        "desc": "Small. Robed. Carries a lantern and a chef's knife. Moves with terrible patience. Its grudge is older than Oakhaven.",
    },
    "malboro": {
        "name": "Malboro",
        "hp": 120, "attack": 12, "defense": 13,
        "xp": 200, "gil": 35, "tier": "hard",
        "desc": "A writhing mass of tentacles and mouths. Its breath alone has ended parties. Do not engage at close range.",
    },
    "dark_knight": {
        "name": "Dark Knight",
        "hp": 110, "attack": 14, "defense": 15,
        "xp": 220, "gil": 80, "tier": "hard",
        "desc": "A fallen warrior animated by dark resonance. Fights with ruthless efficiency. Has no interest in mercy.",
    },
    "iron_giant": {
        "name": "Iron Giant",
        "hp": 180, "attack": 13, "defense": 17,
        "xp": 240, "gil": 60, "tier": "hard",
        "desc": "An armored colossus wielding a greatsword. Each strike shakes the ground. It does not pursue. It does not need to.",
    },
    "jura_aevis": {
        "name": "Jura Aevis",
        "hp": 130, "attack": 13, "defense": 15,
        "xp": 210, "gil": 50, "tier": "hard",
        "desc": "A massive bird of prey. Wingspan blocks the sun. Hunts from above and stoops at killing speed.",
    },
    "magic_dragon": {
        "name": "Magic Dragon",
        "hp": 145, "attack": 14, "defense": 15,
        "xp": 230, "gil": 70, "tier": "hard",
        "desc": "A juvenile dragon that has absorbed residual Aeridorian resonance. Its breath has crystalline properties.",
    },
    "archaeoaevis": {
        "name": "Archeoaevis",
        "hp": 160, "attack": 15, "defense": 16,
        "xp": 250, "gil": 80, "tier": "hard",
        "desc": "An ancient predator, resurrected by ruin-magic. Not adapted to this era. Angrier for it.",
    },
    "titan": {
        "name": "Titan",
        "hp": 200, "attack": 13, "defense": 15,
        "xp": 240, "gil": 55, "tier": "hard",
        "desc": "A creature of pure geological force. The ground shakes when it breathes. It is not attacking you — it simply cannot feel you.",
    },
    "shadow_dancer": {
        "name": "Shadow Dancer",
        "hp": 95, "attack": 16, "defense": 15,
        "xp": 225, "gil": 65, "tier": "hard",
        "desc": "A figure made of concentrated shadow. Moves through walls. Strikes from angles that shouldn't exist.",
    },
    "killer_mantis": {
        "name": "Killer Mantis",
        "hp": 110, "attack": 15, "defense": 14,
        "xp": 215, "gil": 45, "tier": "hard",
        "desc": "An insect the size of a horse. Its foreclaws are serrated. It waits in the deep undergrowth for exactly as long as necessary.",
    },
    "skull_knight": {
        "name": "Skull Knight",
        "hp": 130, "attack": 14, "defense": 16,
        "xp": 235, "gil": 75, "tier": "hard",
        "desc": "Full plate, no occupant. An animated suit of Aeridorian armor that remembers war.",
    },
    "minotaur": {
        "name": "Minotaur",
        "hp": 170, "attack": 13, "defense": 14,
        "xp": 220, "gil": 50, "tier": "hard",
        "desc": "A bull-headed warrior from deep in the ruins. Powerful, furious, and surprisingly tactical.",
    },
    "nachtmahr": {
        "name": "Nachtmahr",
        "hp": 105, "attack": 16, "defense": 14,
        "xp": 230, "gil": 60, "tier": "hard",
        "desc": "A nightmare given form. It appears at the edge of vision, then closer, then too close. Feeds on fear.",
    },
    "crystelle": {
        "name": "Crystelle",
        "hp": 100, "attack": 15, "defense": 17,
        "xp": 225, "gil": 90, "tier": "hard",
        "desc": "An Aeridorian crystalline construct still running its original directives. Those directives involve harm.",
    },
    "birostris": {
        "name": "Birostris",
        "hp": 140, "attack": 13, "defense": 15,
        "xp": 215, "gil": 40, "tier": "hard",
        "desc": "A two-beaked flying creature the color of storm clouds. Discharges lightning passively.",
    },
    "page_256": {
        "name": "Page 256",
        "hp": 1, "attack": 1, "defense": 1,
        "xp": 300, "gil": 200, "tier": "hard",   # FF5 easter egg
        "desc": "Something went wrong. Or right. It's unclear. It falls over if you look at it firmly.",
    },
    "veiled_stalker": {
        "name": "Veiled Stalker",
        "hp": 95, "attack": 17, "defense": 15,
        "xp": 240, "gil": 70, "tier": "hard",
        "desc": "One of the Veiled — the pale race — but gone wrong. Or gone further. It hunts other Veiled now.",
    },
    "soil_ghoul": {
        "name": "Soil Ghoul",
        "hp": 120, "attack": 14, "defense": 14,
        "xp": 210, "gil": 30, "tier": "hard",
        "desc": "Born from the Broken Mire. The swamp has given it mass and patience and very little else.",
    },

    # ══════════════════════════════════════════════════════
    # TIER: DEADLY  (Level 10+)
    # ══════════════════════════════════════════════════════

    "behemoth": {
        "name": "Behemoth",
        "hp": 250, "attack": 17, "defense": 17,
        "xp": 500, "gil": 200, "tier": "deadly",
        "desc": "A massive horned beast the size of a wagon. Its charge levels walls. It is not the biggest thing in the Whisperwood.",
    },
    "dragon": {
        "name": "Ancient Dragon",
        "hp": 300, "attack": 19, "defense": 18,
        "xp": 600, "gil": 400, "tier": "deadly",
        "desc": "A scaled leviathan older than the ruins. Fire breath. Tail crushes steel. It finds you mildly interesting.",
    },
    "lich": {
        "name": "Lich",
        "hp": 200, "attack": 21, "defense": 16,
        "xp": 550, "gil": 300, "tier": "deadly",
        "desc": "An undead sorcerer of immense age. Commands the dead as an afterthought. Its touch drains life in a way that isn't metaphorical.",
    },
    "adamantoise": {
        "name": "Adamantoise",
        "hp": 400, "attack": 13, "defense": 23,
        "xp": 700, "gil": 500, "tier": "deadly",
        "desc": "A mountain-sized tortoise. Shell is effectively impenetrable. Patient. Ancient. Very hard to damage and in no hurry.",
    },
    "omega": {
        "name": "Omega",
        "hp": 500, "attack": 25, "defense": 22,
        "xp": 1000, "gil": 1000, "tier": "deadly",
        "desc": "A weapon of unknown origin. No history. No motive. No language. It simply destroys. Nobody knows who built it or why.",
    },
    "shinryu": {
        "name": "Shinryu",
        "hp": 450, "attack": 23, "defense": 20,
        "xp": 900, "gil": 800, "tier": "deadly",
        "desc": "A divine dragon. It doesn't breathe fire — it breathes something older. Looking directly at it is difficult.",
    },
    "exdeath_tree": {
        "name": "The Accursed Tree",
        "hp": 350, "attack": 20, "defense": 19,
        "xp": 750, "gil": 400, "tier": "deadly",
        "desc": "A massive dead tree at the heart of the deep Whisperwood. It moves. Something is inside it. Something sealed there.",
    },
    "azulmagia": {
        "name": "Azulmagia",
        "hp": 280, "attack": 20, "defense": 18,
        "xp": 650, "gil": 350, "tier": "deadly",
        "desc": "A mage who absorbed too many spells and stopped being a person. Uses everything it has seen against you.",
    },
    "necrophobe": {
        "name": "Necrophobe",
        "hp": 230, "attack": 22, "defense": 17,
        "xp": 600, "gil": 250, "tier": "deadly",
        "desc": "Floats. Surrounded by four barrier shields. Fears nothing but death, which it causes constantly.",
    },
    "gilgamesh": {
        "name": "Gilgamesh",
        "hp": 320, "attack": 18, "defense": 18,
        "xp": 700, "gil": 600, "tier": "deadly",
        "desc": "A wandering warrior with eight arms, each carrying a different weapon. Only one of them is real. He doesn't know which.",
    },
    "apocalypse": {
        "name": "Apocalypse",
        "hp": 380, "attack": 22, "defense": 19,
        "xp": 750, "gil": 350, "tier": "deadly",
        "desc": "It emerged from the Aeridor ruins during a resonance event. It is what happens when Aeridorian magic goes completely wrong.",
    },
    "great_behemoth": {
        "name": "Great Behemoth",
        "hp": 350, "attack": 20, "defense": 18,
        "xp": 650, "gil": 250, "tier": "deadly",
        "desc": "The behemoth you fought before was young. This one is not.",
    },
    "shadow_lich": {
        "name": "Shadow Lich",
        "hp": 270, "attack": 23, "defense": 17,
        "xp": 680, "gil": 320, "tier": "deadly",
        "desc": "A lich that has dissolved its physical form entirely. You cannot stab it. You can only outlast its patience.",
    },
    "cactuar": {
        "name": "Cactuar",
        "hp": 10, "attack": 5, "defense": 20,
        "xp": 500, "gil": 300, "tier": "deadly",  # impossible to hit but trivially weak; pure DEF gimmick
        "desc": "A small spiny cactus creature that runs and fires 1000 needles. Nearly impossible to catch. Worth trying.",
    },
    "antlion": {
        "name": "Sand Worm",
        "hp": 280, "attack": 18, "defense": 16,
        "xp": 580, "gil": 200, "tier": "deadly",
        "desc": "An enormous burrowing predator. The ground gives way and then there is sand and darkness and teeth.",
    },
    "atomos": {
        "name": "Atomos",
        "hp": 310, "attack": 20, "defense": 17,
        "xp": 620, "gil": 300, "tier": "deadly",
        "desc": "A gravity entity. Vast, slow, and possessing a mouth like a collapsed star. It draws things in.",
    },

    # ══════════════════════════════════════════════════════
    # TIER: BOSS  (named encounters, rare/unique)
    # ══════════════════════════════════════════════════════

    "elder_treant": {
        "name": "Elder Treant",
        "hp": 400, "attack": 16, "defense": 16,
        "xp": 800, "gil": 200, "tier": "boss",
        "desc": "The oldest tree in the Whisperwood. It was a person once, in the Aeridor era. It has not forgotten that either.",
    },
    "tonberry_king": {
        "name": "Tonberry King",
        "hp": 300, "attack": 28, "defense": 15,
        "xp": 900, "gil": 500, "tier": "boss",
        "desc": "You killed enough tonberries that the king noticed. It is very, very slow. You will not be able to run forever.",
    },
    "aeridorian_guardian": {
        "name": "Aeridorian Guardian",
        "hp": 450, "attack": 18, "defense": 20,
        "xp": 850, "gil": 400, "tier": "boss",
        "desc": "The final defense construct of Aeridor. It has been waiting in the deepest vault for a thousand years. It is fully operational.",
    },
    "the_hooded_figure": {
        "name": "The Hooded Figure",
        "hp": 350, "attack": 20, "defense": 17,
        "xp": 1000, "gil": 0, "tier": "boss",
        "desc": "The man from the corner of the Stone Hearth. He is not what he appeared to be. He has not appeared to be anything for a very long time.",
    },
    "whisperwood_heart": {
        "name": "Heart of the Whisperwood",
        "hp": 500, "attack": 17, "defense": 18,
        "xp": 1200, "gil": 0, "tier": "boss",
        "desc": "The Whisperwood is not a forest. It is one organism. This is its center. This is what swallowed Aeridor.",
    },
    "elara_turned": {
        "name": "Elder Elara (Turned)",
        "hp": 280, "attack": 19, "defense": 16,
        "xp": 950, "gil": 0, "tier": "boss",
        "desc": "Something has been inside her for a long time. The weight she carries. The warnings she wouldn't give. Now you know why.",
    },
}


# ══════════════════════════════════════════════════════════
# Encounter Tables — what spawns where
# ══════════════════════════════════════════════════════════

ENCOUNTER_TABLES = {
    "whisperwood_edge": [
        ("bat",          12),
        ("goblin",       10),
        ("goblin_guard",  8),
        ("flan",          8),
        ("mud_flan",      8),
        ("grat",          8),
        ("forest_boar",   8),
        ("leaf_bunny",    7),
        ("wisp",          7),
        ("shadow_hound",  7),
        ("nutkin",        6),
        ("myconid",       6),
        ("thorn_lizard",  6),
        ("snipper",       5),
        ("wolf",          4),   # wolves still here but no longer dominant
        ("killer_bee",    3),
        ("microchu",      3),
        ("elf_toad",      3),   # was missing from edge table before
    ],
    "whisperwood_deep": [
        ("wolf",         20),
        ("werewolf",     15),
        ("ghoul",        15),
        ("ghost",        15),
        ("ochu",         12),
        ("harpy",        10),
        ("wind_serpent",  8),
        ("treant",        5),
    ],
    "aeridor_ruins": [
        ("skeleton",      15),
        ("soldier",       15),
        ("gargoyle",      12),
        ("golem",         10),
        ("dark_wizard",   10),
        ("skull_knight",  10),
        ("crystelle",      8),
        ("dark_knight",    8),
        ("tonberry",       7),
        ("lich",           5),
    ],
    "trade_road": [
        ("goblin",        35),
        ("goblin_guard",  20),
        ("bandit",        25),
        ("wolf",          15),
        ("cockatrice",     5),
    ],
    "whisperwood_deep_night": [   # future: time-of-day variation
        ("ghost",         25),
        ("ghoul",         20),
        ("nachtmahr",     20),
        ("shadow_dancer", 15),
        ("werewolf",      15),
        ("lich",           5),
    ],
}

# Gil drop multiplier for boss tier (bosses don't drop standard gil)
BOSS_GIL_DROP = 0


# ══════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════

def get(name: str) -> dict | None:
    """
    Look up a monster by key. Case-insensitive with fuzzy fallback.
    Returns a deep copy (caller may mutate HP safely).
    """
    import copy
    key = name.lower().strip().replace(" ", "_").replace("-", "_")

    # Exact match
    if key in MONSTERS:
        return copy.deepcopy(MONSTERS[key])

    # Partial match (unique)
    matches = [k for k in MONSTERS if key in k or k in key]
    if len(matches) == 1:
        return copy.deepcopy(MONSTERS[matches[0]])

    # Name field match
    name_str = str(name).lower()
    for k, v in MONSTERS.items():
        v_name = str(v.get("name", "")).lower()
        if name_str in v_name or v_name in name_str:
            return copy.deepcopy(MONSTERS[k])

    return None




def list_by_tier(tier: str) -> list[tuple[str, dict]]:
    """Return all monsters of a given tier."""
    return [(k, v) for k, v in MONSTERS.items() if v["tier"] == tier]


def format_bestiary() -> str:
    """Format full bestiary for Discord — paginated by tier."""
    tiers = ["trivial", "easy", "medium", "hard", "deadly", "boss"]
    lines = []
    for tier in tiers:
        monsters = list_by_tier(tier)
        if not monsters:
            continue
        lines.append(f"\n**── {tier.upper()} ──**")
        for key, m in sorted(monsters, key=lambda x: x[1]["hp"]):
            lines.append(
                f"`{key:<22}` {m['name']:<22} "
                f"HP:{m['hp']:>4}  ATK:{m['attack']:>3}  DEF:{m['defense']:>3}  "
                f"XP:{m['xp']:>5}  Gil:{m['gil']:>4}"
            )
    return "\n".join(lines)


TIER_COUNTS = {
    "trivial": len(list_by_tier("trivial")),
    "easy":    len(list_by_tier("easy")),
    "medium":  len(list_by_tier("medium")),
    "hard":    len(list_by_tier("hard")),
    "deadly":  len(list_by_tier("deadly")),
    "boss":    len(list_by_tier("boss")),
}