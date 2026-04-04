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
        "hp": 18, "attack": 3, "defense": 9,
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
        "hp": 20, "attack": 3, "defense": 8,
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
        "hp": 18, "attack": 4, "defense": 8,
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
        "hp": 20, "attack": 2, "defense": 7,
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
        "hp": 15, "attack": 4, "defense": 8,
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
        "hp": 16, "attack": 4, "defense": 10,
        "xp": 28, "gil": 6, "tier": "trivial",
        "desc": "A dog-shaped shadow that has developed opinions about territory.",
    },

    "fire_beetle": {
        "name": "Fire Beetle",
        "hp": 14, "attack": 3, "defense": 8,
        "xp": 18, "gil": 3, "tier": "trivial",
        "desc": "A beetle the size of a dog with a glowing thorax. Bites leave minor burns. Common near warm rocks.",
    },
    "large_bat": {
        "name": "Large Bat",
        "hp": 12, "attack": 4, "defense": 9,
        "xp": 16, "gil": 2, "tier": "trivial",
        "desc": "A bat with a wingspan wider than a man's arms. Echolocation makes it hard to surprise.",
    },
    "gnoll_pup": {
        "name": "Gnoll Pup",
        "hp": 18, "attack": 4, "defense": 9,
        "xp": 22, "gil": 5, "tier": "trivial",
        "desc": "A young hyena-man. Scrawny and mean. Already knows how to hold a weapon.",
    },
    "decaying_skeleton": {
        "name": "Decaying Skeleton",
        "hp": 15, "attack": 3, "defense": 7,
        "xp": 16, "gil": 3, "tier": "trivial",
        "desc": "Barely held together by old magic. Falls apart if hit hard enough. Reassembles if you don't finish it.",
    },
    "spiderling": {
        "name": "Spiderling",
        "hp": 8, "attack": 5, "defense": 10,
        "xp": 20, "gil": 2, "tier": "trivial",
        "desc": "A young forest spider. Fast, venomous, and angry about being small.",
    },
    "hornet": {
        "name": "Hornet",
        "hp": 10, "attack": 4, "defense": 11,
        "xp": 18, "gil": 2, "tier": "trivial",
        "desc": "A wasp the length of a forearm. Stings paralyze smaller creatures. You are not a smaller creature. Probably.",
    },
    "imp": {
        "name": "Imp",
        "hp": 12, "attack": 5, "defense": 10,
        "xp": 24, "gil": 6, "tier": "trivial",
        "desc": "A tiny devil-creature with bat wings. Throws sparks and insults. Annoying beyond its threat level.",
    },
    "leg_eater": {
        "name": "Leg Eater",
        "hp": 16, "attack": 3, "defense": 8,
        "xp": 18, "gil": 4, "tier": "trivial",
        "desc": "A carnivorous plant that snaps at ankles. Sessile until you step on it.",
    },
    "wererat": {
        "name": "Wererat",
        "hp": 14, "attack": 4, "defense": 9,
        "xp": 20, "gil": 5, "tier": "trivial",
        "desc": "A rat that walks upright and carries a shiv. Found near sewers and basements. Clever enough to ambush.",
    },
    "kobold": {
        "name": "Kobold",
        "hp": 15, "attack": 4, "defense": 8,
        "xp": 20, "gil": 4, "tier": "trivial",
        "desc": "A small, reptilian humanoid. Draconic in lineage, but cowardly in practice. Usually found in large, annoying numbers.",
    },
    "giant_rat_mtg": {
        "name": "Giant Rat",
        "hp": 12, "attack": 3, "defense": 7,
        "xp": 15, "gil": 2, "tier": "trivial",
        "desc": "An unnaturally large rodent. Its bite is infectious and its hunger is bottomless.",
    },
    "goblin_guide": {
        "name": "Goblin Guide",
        "hp": 18, "attack": 5, "defense": 9,
        "xp": 25, "gil": 6, "tier": "trivial",
        "desc": "A frantic goblin that knows the shortcuts. It'll lead you straight to your doom if you aren't careful.",
    },
    "llanowar_scout": {
        "name": "Llanowar Scout",
        "hp": 16, "attack": 4, "defense": 11,
        "xp": 18, "gil": 3, "tier": "trivial",
        "desc": "An elf from a distant woodland. Skilled in woodcraft and defensive strikes.",
    },
    "cave_crawler": {
        "name": "Cave Crawler",
        "hp": 14, "attack": 3, "defense": 12,
        "xp": 20, "gil": 4, "tier": "trivial",
        "desc": "A multi-legged insectoid that clings to cave ceilings. Drops on unsuspecting prey.",
    },
    "slime": {
        "name": "Slime",
        "hp": 10, "attack": 2, "defense": 15,
        "xp": 12, "gil": 1, "tier": "trivial",
        "desc": "A quiver of jelly. Hard to hurt with a blade, but weak to almost everything else.",
    },
    "stirge": {
        "name": "Stirge",
        "hp": 8, "attack": 4, "defense": 10,
        "xp": 15, "gil": 2, "tier": "trivial",
        "desc": "A winged insect-bird that drains blood. They are rarely alone.",
    },
    "giant_centipede": {
        "name": "Giant Centipede",
        "hp": 12, "attack": 3, "defense": 9,
        "xp": 18, "gil": 3, "tier": "trivial",
        "desc": "A massive multi-legged horror. Its mandibles drip with a numbing toxin.",
    },
    "mudbrawler": {
        "name": "Mudbrawler",
        "hp": 18, "attack": 4, "defense": 7,
        "xp": 20, "gil": 4, "tier": "trivial",
        "desc": "A goblinoid creature that thrives in filth and chaos. It fights with clumsy but heavy strikes.",
    },
    "homunculus": {
        "name": "Homunculus",
        "hp": 10, "attack": 3, "defense": 10,
        "xp": 15, "gil": 2, "tier": "trivial",
        "desc": "A tiny, artificial humanoid. It follows its master's telepathic commands with eerie precision.",
    },
    "vegepygmy": {
        "name": "Vegepygmy",
        "hp": 15, "attack": 4, "defense": 9,
        "xp": 20, "gil": 3, "tier": "trivial",
        "desc": "A fungal creature spawned from the remains of others. It communicates through rhythmic thumping.",
    },
    "xvart": {
        "name": "Xvart",
        "hp": 12, "attack": 3, "defense": 8,
        "xp": 18, "gil": 4, "tier": "trivial",
        "desc": "A small, blue-skinned humanoid that worships a minor god of thievery. They are greedy and paranoid.",
    },
    "mud_element": {
        "name": "Mud Element",
        "hp": 20, "attack": 4, "defense": 7,
        "xp": 22, "gil": 3, "tier": "trivial",
        "desc": "A sludge-like creature that slows anyone who steps into its reach.",
    },
    "hand_axe_goblin": {
        "name": "Hand Axe Goblin",
        "hp": 20, "attack": 5, "defense": 9,
        "xp": 28, "gil": 7, "tier": "trivial",
        "desc": "A goblin with better equipment and worse manners. Throws hand axes before charging.",
    },
    "skeleton_archer": {
        "name": "Skeleton Archer",
        "hp": 22, "attack": 6, "defense": 10,
        "xp": 35, "gil": 8, "tier": "trivial",
        "desc": "A skeleton that still remembers how to draw a bow. Its aim is disturbingly good.",
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

    "gnoll": {
        "name": "Gnoll",
        "hp": 35, "attack": 6, "defense": 10,
        "xp": 48, "gil": 12, "tier": "easy",
        "desc": "A full-grown hyena-man. Hunts in packs. Laughs before it charges. The laugh is worse.",
    },
    "orc_pawn": {
        "name": "Orc Pawn",
        "hp": 30, "attack": 5, "defense": 10,
        "xp": 42, "gil": 9, "tier": "easy",
        "desc": "An orc foot soldier. Disciplined, armored, and expendable. There are always more.",
    },
    "orc_centurion": {
        "name": "Orc Centurion",
        "hp": 40, "attack": 7, "defense": 12,
        "xp": 58, "gil": 14, "tier": "easy",
        "desc": "An orc officer. Better armor, better weapon, worse attitude. Commands squads of pawns.",
    },
    "basilisk": {
        "name": "Basilisk",
        "hp": 38, "attack": 6, "defense": 11,
        "xp": 55, "gil": 15, "tier": "easy",
        "desc": "An eight-legged reptile with a petrifying gaze. Keep your shield up and your eyes down.",
    },
    "bomb": {
        "name": "Bomb",
        "hp": 25, "attack": 8, "defense": 9,
        "xp": 55, "gil": 10, "tier": "easy",
        "desc": "A floating sphere of compressed fire. It gets bigger when you hit it. Then it explodes.",
    },
    "coeurl": {
        "name": "Coeurl",
        "hp": 34, "attack": 7, "defense": 11,
        "xp": 52, "gil": 12, "tier": "easy",
        "desc": "A panther-like predator with whip-like whiskers that discharge lightning. Silent until it strikes.",
    },
    "grenade": {
        "name": "Grenade",
        "hp": 30, "attack": 9, "defense": 9,
        "xp": 58, "gil": 12, "tier": "easy",
        "desc": "A bomb that has been burning long enough to develop opinions. Larger, angrier, redder.",
    },
    "pugil": {
        "name": "Pugil",
        "hp": 28, "attack": 6, "defense": 10,
        "xp": 45, "gil": 8, "tier": "easy",
        "desc": "A carnivorous fish that has grown legs and a foul temper. Found near Tricklebrook. Surprisingly fast on land.",
    },
    "revenant": {
        "name": "Revenant",
        "hp": 40, "attack": 7, "defense": 11,
        "xp": 52, "gil": 0, "tier": "easy",
        "desc": "An undead warrior with enough memory to hold a grudge. Attacks with purpose, not instinct.",
    },
    "gnoll_hunter": {
        "name": "Gnoll Hunter",
        "hp": 45, "attack": 7, "defense": 11,
        "xp": 60, "gil": 15, "tier": "easy",
        "desc": "A gnoll that has mastered the bow. It tracks its prey for miles before striking from the shadows.",
    },
    "bugbear": {
        "name": "Bugbear",
        "hp": 55, "attack": 8, "defense": 12,
        "xp": 75, "gil": 20, "tier": "easy",
        "desc": "A hulking, hairy goblinoid. Surprisingly stealthy for its size. Hits with the force of a falling tree.",
    },
    "rust_monster": {
        "name": "Rust Monster",
        "hp": 30, "attack": 6, "defense": 14,
        "xp": 65, "gil": 0, "tier": "easy",
        "desc": "An insect-like creature that feeds on metal. Your armor is looking quite delicious to it.",
    },
    "harpy_dd": {
        "name": "Harpy",
        "hp": 40, "attack": 7, "defense": 10,
        "xp": 55, "gil": 12, "tier": "easy",
        "desc": "A creature with the upper body of a woman and the lower body of a bird. Its song lures travelers to their deaths.",
    },
    "vampire_nighthawk": {
        "name": "Vampire Nighthawk",
        "hp": 35, "attack": 9, "defense": 11,
        "xp": 80, "gil": 18, "tier": "easy",
        "desc": "A winged predator that drains the life of its victims. It strikes with precision and lethal intent.",
    },
    "kenku": {
        "name": "Kenku",
        "hp": 30, "attack": 6, "defense": 11,
        "xp": 50, "gil": 15, "tier": "easy",
        "desc": "A flightless bird-man. They mimic sounds to lure prey and communicate in whistles and clicks.",
    },
    "lizardfolk_dd": {
        "name": "Lizardfolk",
        "hp": 45, "attack": 7, "defense": 13,
        "xp": 65, "gil": 12, "tier": "easy",
        "desc": "Cold-blooded warriors of the swamp. They are efficient hunters and scavengers.",
    },
    "thri_kreen": {
        "name": "Thri-Kreen",
        "hp": 38, "attack": 8, "defense": 12,
        "xp": 70, "gil": 10, "tier": "easy",
        "desc": "An insectoid nomad with four arms. They are masters of the desert and waste.",
    },
    "sea_serpent_ff": {
        "name": "Sea Serpent",
        "hp": 60, "attack": 8, "defense": 10,
        "xp": 85, "gil": 25, "tier": "easy",
        "desc": "A smaller cousin of the great dragons. It haunts the coastal waters and river mouths.",
    },
    "grimlock": {
        "name": "Grimlock",
        "hp": 40, "attack": 7, "defense": 12,
        "xp": 60, "gil": 15, "tier": "easy",
        "desc": "A blind, stone-skinned humanoid from the deep underground. It senses vibrations with uncanny accuracy.",
    },
    "skum": {
        "name": "Skum",
        "hp": 35, "attack": 6, "defense": 11,
        "xp": 55, "gil": 12, "tier": "easy",
        "desc": "A warped, aquatic slave of the aboleths. It is a creature of pure, mindless servitude.",
    },
    "troglodyte": {
        "name": "Troglodyte",
        "hp": 42, "attack": 7, "defense": 13,
        "xp": 65, "gil": 10, "tier": "easy",
        "desc": "A lizard-like subterranean dweller. Its stench is so foul it can weaken the strongest warriors.",
    },
    "zu_ff": {
        "name": "Zu",
        "hp": 65, "attack": 9, "defense": 10,
        "xp": 90, "gil": 30, "tier": "easy",
        "desc": "A giant bird of prey that can snatch up a horse in its talons. Its wings create gale-force gusts.",
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

    "hill_gigas": {
        "name": "Hill Gigas",
        "hp": 90, "attack": 10, "defense": 12,
        "xp": 105, "gil": 25, "tier": "medium",
        "desc": "A giant the height of two men. Throws boulders. Not smart enough to aim well, but doesn't need to be.",
    },
    "fire_gigas": {
        "name": "Fire Gigas",
        "hp": 95, "attack": 11, "defense": 13,
        "xp": 115, "gil": 30, "tier": "medium",
        "desc": "A giant wreathed in flame. The ground chars where it walks. Its fists ignite on impact.",
    },
    "griffon": {
        "name": "Griffon",
        "hp": 75, "attack": 10, "defense": 13,
        "xp": 100, "gil": 22, "tier": "medium",
        "desc": "Eagle head, lion body. Nests on the ruins' highest spires. Protective of territory and young.",
    },
    "mindflayer": {
        "name": "Mindflayer",
        "hp": 60, "attack": 13, "defense": 12,
        "xp": 125, "gil": 40, "tier": "medium",
        "desc": "A tentacle-faced horror that feeds on thoughts. You forget what you were fighting mid-swing.",
    },
    "naga": {
        "name": "Naga",
        "hp": 70, "attack": 10, "defense": 13,
        "xp": 110, "gil": 28, "tier": "medium",
        "desc": "A serpent-bodied woman with a trident and ancient spite. Guards waterways and drowned places.",
    },
    "ogre": {
        "name": "Ogre",
        "hp": 85, "attack": 10, "defense": 11,
        "xp": 95, "gil": 20, "tier": "medium",
        "desc": "A hulking brute with a tree trunk for a weapon. Stupid and strong in exactly that order.",
    },
    "spectre": {
        "name": "Spectre",
        "hp": 50, "attack": 12, "defense": 14,
        "xp": 115, "gil": 0, "tier": "medium",
        "desc": "A ghost that has given up on mourning and moved on to malice. Drains warmth from the air.",
    },
    "troll": {
        "name": "Troll",
        "hp": 95, "attack": 9, "defense": 11,
        "xp": 100, "gil": 18, "tier": "medium",
        "desc": "A gangly, grey-skinned brute that regenerates. You have to burn the pieces or they crawl back together.",
    },
    "dullahan": {
        "name": "Dullahan",
        "hp": 80, "attack": 12, "defense": 14,
        "xp": 120, "gil": 35, "tier": "medium",
        "desc": "A headless knight on a headless horse. Carries its skull under one arm. The skull watches you.",
    },
    "sand_angler": {
        "name": "Sand Angler",
        "hp": 65, "attack": 9, "defense": 12,
        "xp": 90, "gil": 15, "tier": "medium",
        "desc": "Buries itself in the road dust and waits. Its mandibles close faster than you can react.",
    },
    "gelatinous_cube": {
        "name": "Gelatinous Cube",
        "hp": 60, "attack": 8, "defense": 10,
        "xp": 80, "gil": 15, "tier": "medium",
        "desc": "A transparent cube of acid and hunger. It moves silent and slow, digesting everything it touches.",
    },
    "nightmare_mtg": {
        "name": "Nightmare",
        "hp": 55, "attack": 11, "defense": 13,
        "xp": 100, "gil": 25, "tier": "medium",
        "desc": "An undead horse wreathed in dark flames. It leaves scorched hoofprints and the smell of ozone.",
    },
    "gorgon_dd": {
        "name": "Gorgon",
        "hp": 60, "attack": 10, "defense": 15,
        "xp": 110, "gil": 20, "tier": "medium",
        "desc": "A scale-covered bull with a breath that turns creatures to stone. Its hide is as hard as iron.",
    },
    "mimic": {
        "name": "Mimic",
        "hp": 50, "attack": 12, "defense": 13,
        "xp": 120, "gil": 50, "tier": "medium",
        "desc": "A creature that takes the form of inanimate objects. Its tongue is sticky and its teeth are numerous.",
    },
    "air_elemental": {
        "name": "Air Elemental",
        "hp": 55, "attack": 11, "defense": 14,
        "xp": 100, "gil": 10, "tier": "medium",
        "desc": "A living whirlwind. It strikes with the force of a hurricane and vanishes as quickly as it appears.",
    },
    "bulette": {
        "name": "Bulette",
        "hp": 90, "attack": 12, "defense": 17,
        "xp": 150, "gil": 40, "tier": "medium",
        "desc": "The 'land shark'. It burrows through the earth and leaps out to consume its prey in a single bite.",
    },
    "hook_horror": {
        "name": "Hook Horror",
        "hp": 75, "attack": 11, "defense": 14,
        "xp": 120, "gil": 25, "tier": "medium",
        "desc": "An avian-insectoid hybrid that climbs cave walls with massive, hooked claws. It communicates through clicks.",
    },
    "umber_hulk": {
        "name": "Umber Hulk",
        "hp": 95, "attack": 13, "defense": 15,
        "xp": 180, "gil": 50, "tier": "medium",
        "desc": "A massive, ape-like insectoid with eyes that can confuse the mind. It is a master of subterranean ambush.",
    },
    "owlbear": {
        "name": "Owlbear",
        "hp": 75, "attack": 10, "defense": 13,
        "xp": 100, "gil": 20, "tier": "medium",
        "desc": "A feathered horror — part owl, part bear, all fury. It charges through undergrowth without slowing.",
    },
    "displacer_beast": {
        "name": "Displacer Beast",
        "hp": 65, "attack": 11, "defense": 14,
        "xp": 110, "gil": 25, "tier": "medium",
        "desc": "A six-legged panther that bends light around itself. It's never quite where it appears to be.",
    },
    "ettercap": {
        "name": "Ettercap",
        "hp": 55, "attack": 9, "defense": 12,
        "xp": 90, "gil": 18, "tier": "medium",
        "desc": "A spider-like humanoid that weaves traps of web and malice. Found near Whisperwood nests.",
    },
    "chimera_dd": {
        "name": "Chimera",
        "hp": 80, "attack": 11, "defense": 13,
        "xp": 115, "gil": 30, "tier": "medium",
        "desc": "Three heads, three breaths, one bad attitude. The goat head is the most dangerous — it bites.",
    },
    "serra_angel": {
        "name": "Serra Angel",
        "hp": 70, "attack": 10, "defense": 15,
        "xp": 120, "gil": 35, "tier": "medium",
        "desc": "A radiant winged warrior from a forgotten age. She guards something that no longer exists.",
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

    "drake": {
        "name": "Drake",
        "hp": 130, "attack": 14, "defense": 15,
        "xp": 220, "gil": 55, "tier": "hard",
        "desc": "A wingless dragon. What it lacks in flight it makes up for in sheer armored mass and fire breath.",
    },
    "medusa": {
        "name": "Medusa",
        "hp": 100, "attack": 15, "defense": 14,
        "xp": 230, "gil": 70, "tier": "hard",
        "desc": "A woman with snakes for hair and a gaze that turns flesh to stone. Don't look at her face.",
    },
    "ghast": {
        "name": "Ghast",
        "hp": 110, "attack": 14, "defense": 13,
        "xp": 200, "gil": 45, "tier": "hard",
        "desc": "A ghoul that has fed enough to evolve. Paralyzing touch, rotting stench, and a hunger that never ends.",
    },
    "wight": {
        "name": "Wight",
        "hp": 120, "attack": 15, "defense": 14,
        "xp": 215, "gil": 55, "tier": "hard",
        "desc": "An undead lord that drains life with a touch. Where it walks, plants wither and animals flee.",
    },
    "wyrm": {
        "name": "Wyrm",
        "hp": 150, "attack": 14, "defense": 16,
        "xp": 240, "gil": 65, "tier": "hard",
        "desc": "An adolescent dragon. Already dangerous. In a century it will be devastating. Best dealt with now.",
    },
    "spectral_knight": {
        "name": "Spectral Knight",
        "hp": 125, "attack": 15, "defense": 16,
        "xp": 235, "gil": 80, "tier": "hard",
        "desc": "An Aeridorian champion who refused death. Fights with skill perfected over a thousand years of undeath.",
    },
    "clay_golem": {
        "name": "Clay Golem",
        "hp": 160, "attack": 12, "defense": 16,
        "xp": 210, "gil": 30, "tier": "hard",
        "desc": "Animated clay given purpose by ancient wards. Slow but utterly relentless. Absorbs blunt damage.",
    },
    "death_claw": {
        "name": "Death Claw",
        "hp": 105, "attack": 16, "defense": 14,
        "xp": 225, "gil": 50, "tier": "hard",
        "desc": "A massive crustacean with claws that can sever a horse. Found in deep cave systems beneath the ruins.",
    },
    "beholder": {
        "name": "Beholder",
        "hp": 180, "attack": 18, "defense": 17,
        "xp": 450, "gil": 150, "tier": "hard",
        "desc": "A floating orb of eyes and madness. Each eye stalk can fire a different deadly ray.",
    },
    "mind_flayer": {
        "name": "Mind Flayer",
        "hp": 140, "attack": 16, "defense": 15,
        "xp": 400, "gil": 120, "tier": "hard",
        "desc": "An illithid master of psionics. It hungers for brains and enslaves the wills of the weak.",
    },
    "rakshasa": {
        "name": "Rakshasa",
        "hp": 160, "attack": 15, "defense": 18,
        "xp": 380, "gil": 200, "tier": "hard",
        "desc": "A tiger-headed fiend and master of illusion. Its hands are backwards, and its heart is pure malice.",
    },
    "iron_giant_ff": {
        "name": "Iron Giant",
        "hp": 250, "attack": 20, "defense": 22,
        "xp": 500, "gil": 250, "tier": "hard",
        "desc": "A massive, plate-armored golem with a cleaver the size of a man. It exists only to crush.",
    },
    "craw_wurm": {
        "name": "Craw Wurm",
        "hp": 220, "attack": 16, "defense": 14,
        "xp": 350, "gil": 80, "tier": "hard",
        "desc": "A worm so large it can swallow whole wagons. It moves with a crushing weight through the deep forest.",
    },
    "bone_devil": {
        "name": "Bone Devil",
        "hp": 170, "attack": 17, "defense": 19,
        "xp": 420, "gil": 140, "tier": "hard",
        "desc": "A skeletal fiend with a stinging tail. It is a merciless enforcer of hell's laws.",
    },
    "death_tyrant": {
        "name": "Death Tyrant",
        "hp": 200, "attack": 20, "defense": 18,
        "xp": 600, "gil": 200, "tier": "hard",
        "desc": "An undead beholder. Its eye stalks glow with a sickly red light, and its gaze is the very chill of the grave.",
    },
    "drider": {
        "name": "Drider",
        "hp": 150, "attack": 16, "defense": 17,
        "xp": 450, "gil": 100, "tier": "hard",
        "desc": "A drow transformed into a half-spider monstrosity. It is a cursed weaver of webs and shadow.",
    },
    "storm_giant": {
        "name": "Storm Giant",
        "hp": 300, "attack": 22, "defense": 20,
        "xp": 700, "gil": 300, "tier": "hard",
        "desc": "A titan of the heights. It commands the lightning and the thunder with a word.",
    },
    "balor_dd": {
        "name": "Balor",
        "hp": 350, "attack": 25, "defense": 22,
        "xp": 1500, "gil": 1000, "tier": "hard",
        "desc": "A towering demon of fire and shadow. It wields a flaming sword and a multi-tailed whip of lightning.",
    },
    "glabrezu": {
        "name": "Glabrezu",
        "hp": 220, "attack": 20, "defense": 19,
        "xp": 800, "gil": 400, "tier": "hard",
        "desc": "A demon that tempts with power and wealth, only to crush its victims with its massive claws.",
    },
    "hezrou": {
        "name": "Hezrou",
        "hp": 180, "attack": 18, "defense": 17,
        "xp": 600, "gil": 200, "tier": "hard",
        "desc": "A toad-like demon of filth and disease. Its presence is an affront to the senses.",
    },
    "marilith": {
        "name": "Marilith",
        "hp": 260, "attack": 22, "defense": 20,
        "xp": 1000, "gil": 600, "tier": "hard",
        "desc": "A six-armed serpent demon. She is a master of the blade, striking with a whirlwind of steel.",
    },
    "vrock": {
        "name": "Vrock",
        "hp": 160, "attack": 16, "defense": 16,
        "xp": 500, "gil": 150, "tier": "hard",
        "desc": "A vulture-headed demon of greed. Its screech can stun those who witness its horrific dance.",
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

    "king_behemoth": {
        "name": "King Behemoth",
        "hp": 380, "attack": 22, "defense": 19,
        "xp": 700, "gil": 300, "tier": "deadly",
        "desc": "The apex predator. Horns like battering rams, hide like castle walls. Everything else is prey.",
    },
    "red_dragon": {
        "name": "Red Dragon",
        "hp": 320, "attack": 20, "defense": 18,
        "xp": 650, "gil": 350, "tier": "deadly",
        "desc": "A mature dragon with scales the color of cooling lava. Its fire breath melts stone.",
    },
    "frost_dragon": {
        "name": "Frost Dragon",
        "hp": 310, "attack": 19, "defense": 19,
        "xp": 640, "gil": 340, "tier": "deadly",
        "desc": "A dragon of ice and wind. Its breath freezes blood in the veins. Nests in the highest peaks.",
    },
    "iron_golem": {
        "name": "Iron Golem",
        "hp": 350, "attack": 18, "defense": 22,
        "xp": 620, "gil": 200, "tier": "deadly",
        "desc": "An Aeridorian war machine of solid iron. Immune to most magic. Hits like a collapsing bridge.",
    },
    "vampire_lord": {
        "name": "Vampire Lord",
        "hp": 260, "attack": 21, "defense": 17,
        "xp": 600, "gil": 280, "tier": "deadly",
        "desc": "An ancient undead aristocrat. Charms, drains, and vanishes. Has been planning this encounter for decades.",
    },
    "hydra": {
        "name": "Hydra",
        "hp": 340, "attack": 19, "defense": 17,
        "xp": 650, "gil": 250, "tier": "deadly",
        "desc": "A multi-headed serpent. Cut one head off and two grow back. Fire is the answer, if you can get close enough.",
    },
    "dark_rider": {
        "name": "Dark Rider",
        "hp": 280, "attack": 22, "defense": 18,
        "xp": 680, "gil": 320, "tier": "deadly",
        "desc": "A horseman in black plate that appears on the trade road at midnight. Those who flee say his lance never misses.",
    },
    "tiamat_avatar": {
        "name": "Avatar of Tiamat",
        "hp": 500, "attack": 25, "defense": 22,
        "xp": 1200, "gil": 1000, "tier": "deadly",
        "desc": "A five-headed dragon aspect. Each head breathes a different form of elemental destruction.",
    },
    "nicol_bolas_echo": {
        "name": "Echo of Nicol Bolas",
        "hp": 450, "attack": 28, "defense": 20,
        "xp": 1500, "gil": 0, "tier": "deadly",
        "desc": "A fragment of the elder dragon planeswalker. Even a shadow of his brilliance is enough to shatter worlds.",
    },
    "bahamut_ff": {
        "name": "Bahamut",
        "hp": 550, "attack": 26, "defense": 24,
        "xp": 2000, "gil": 1500, "tier": "deadly",
        "desc": "The King of Dragons. His 'Megaflare' is the stuff of legends and nightmares.",
    },
    "shivan_dragon": {
        "name": "Shivan Dragon",
        "hp": 400, "attack": 24, "defense": 20,
        "xp": 1000, "gil": 500, "tier": "deadly",
        "desc": "The master of the Shiv mountains. Its breath is an endless torrent of fire.",
    },
    "death_knight_dd": {
        "name": "Death Knight",
        "hp": 380, "attack": 22, "defense": 25,
        "xp": 900, "gil": 400, "tier": "deadly",
        "desc": "A fallen paladin that has traded its soul for eternal undeath and unholy power.",
    },
    "ancient_red_dragon": {
        "name": "Ancient Red Dragon",
        "hp": 800, "attack": 32, "defense": 28,
        "xp": 5000, "gil": 10000, "tier": "deadly",
        "desc": "The ultimate incarnation of greed and fire. Its mere presence can scorch the earth for miles.",
    },
    "tarrasque": {
        "name": "The Tarrasque",
        "hp": 999, "attack": 35, "defense": 30,
        "xp": 10000, "gil": 0, "tier": "deadly",
        "desc": "A legendary engine of pure destruction. It does not think; it only consumes and destroys.",
    },
    "kraken_dd": {
        "name": "Kraken",
        "hp": 600, "attack": 28, "defense": 22,
        "xp": 3000, "gil": 2000, "tier": "deadly",
        "desc": "The terror of the deep. Its tentacles can drag the largest ships to a watery grave.",
    },
    "demogorgon_echo": {
        "name": "Echo of Demogorgon",
        "hp": 700, "attack": 32, "defense": 26,
        "xp": 4000, "gil": 0, "tier": "deadly",
        "desc": "The Prince of Demons. His two heads, Aameul and Hethradiah, are locked in eternal conflict.",
    },
    "orcus_aspect": {
        "name": "Aspect of Orcus",
        "hp": 650, "attack": 30, "defense": 25,
        "xp": 3500, "gil": 0, "tier": "deadly",
        "desc": "The Demon Prince of Undeath. He wields a skull-tipped wand that can extinguish life with a touch.",
    },
    "grazzt_avatar": {
        "name": "Avatar of Graz'zt",
        "hp": 600, "attack": 28, "defense": 24,
        "xp": 3000, "gil": 0, "tier": "deadly",
        "desc": "The Dark Prince of Pleasure. He is a master of seduction and strategic cruelty.",
    },
    "juiblex_shadow": {
        "name": "Shadow of Juiblex",
        "hp": 550, "attack": 24, "defense": 22,
        "xp": 2500, "gil": 0, "tier": "deadly",
        "desc": "The Faceless Lord. A bubbling mass of slime and eyes that dissolves everything it touches.",
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
    "vecna_lich_god": {
        "name": "Vecna, the Whispered One",
        "hp": 600, "attack": 30, "defense": 25,
        "xp": 5000, "gil": 0, "tier": "boss",
        "desc": "The god of secrets and undeath. He watches from the hollow heart of existence.",
    },
    "acererak": {
        "name": "Acererak the Eternal",
        "hp": 550, "attack": 28, "defense": 24,
        "xp": 4500, "gil": 0, "tier": "boss",
        "desc": "A planes-hopping lich who builds tombs for the sole purpose of harvesting souls.",
    },
    "chaos_ff1": {
        "name": "Chaos",
        "hp": 700, "attack": 32, "defense": 26,
        "xp": 6000, "gil": 0, "tier": "boss",
        "desc": "The source of all ruin. A cycle of hatred and power that spans across time.",
    },
    "zeromus_ff4": {
        "name": "Zeromus",
        "hp": 800, "attack": 34, "defense": 28,
        "xp": 7000, "gil": 0, "tier": "boss",
        "desc": "The embodiment of pure spite. It does not exist, yet its hatred is absolute.",
    },
    "lord_soth": {
        "name": "Lord Soth",
        "hp": 450, "attack": 26, "defense": 24,
        "xp": 3500, "gil": 500, "tier": "boss",
        "desc": "The Knight of the Rose, now a Death Knight. His word is death, and his touch is the grave.",
    },

    "exdeath_ff5": {
        "name": "Exdeath",
        "hp": 850, "attack": 32, "defense": 26,
        "xp": 8000, "gil": 0, "tier": "boss",
        "desc": "A tree born of ancient malice. He seeks to return all to the Void.",
    },
    "shinryu_ff5": {
        "name": "Shinryu",
        "hp": 999, "attack": 38, "defense": 30,
        "xp": 12000, "gil": 5000, "tier": "boss",
        "desc": "A dragon from the Rift. He is the master of elemental devastation and cosmic power.",
    },
    "omega_ff5": {
        "name": "Omega",
        "hp": 900, "attack": 36, "defense": 35,
        "xp": 10000, "gil": 0, "tier": "boss",
        "desc": "An ancient machine of war. its defense is impenetrable, and its fire is absolute.",
    },
    "kefka_ascended": {
        "name": "Kefka (Ascended)",
        "hp": 750, "attack": 34, "defense": 24,
        "xp": 9000, "gil": 0, "tier": "boss",
        "desc": "A mad court mage who has stolen the power of gods. He laughs as the world burns.",
    },
    "sephiroth_echo": {
        "name": "Echo of Sephiroth",
        "hp": 700, "attack": 36, "defense": 22,
        "xp": 8500, "gil": 0, "tier": "boss",
        "desc": "A silver-haired angel of death. He moves with a grace that belies his terrifying power.",
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
        ("bat",               10),
        ("goblin",             8),
        ("goblin_guard",       6),
        ("flan",               6),
        ("mud_flan",           6),
        ("grat",               6),
        ("forest_boar",        6),
        ("leaf_bunny",         5),
        ("wisp",               5),
        ("shadow_hound",       5),
        ("nutkin",             5),
        ("myconid",            5),
        ("thorn_lizard",       5),
        ("snipper",            4),
        ("wolf",               3),
        ("killer_bee",         3),
        ("microchu",           3),
        ("elf_toad",           3),
        ("kobold",             8),
        ("giant_rat_mtg",      7),
        ("slime",              7),
        ("stirge",             6),
        ("vegepygmy",          5),
        ("homunculus",         4),
        ("sahagin",            4),
        ("llanowar_scout",     3),
        ("mud_element",        3),
        ("skum",               3),
        ("fire_beetle",        5),
        ("large_bat",          4),
        ("gnoll_pup",          4),
        ("spiderling",         4),
        ("hornet",             3),
        ("imp",                3),
        ("leg_eater",          3),
        ("wererat",            3),
        ("decaying_skeleton",  3),
        ("black_flan",         4),
        ("moldwynd",           4),
        ("blood_slime",        4),
        ("snow_bunny",         3),
        ("ice_wisp",           3),
        ("summer_hornet",      3),
        ("zombie",             3),
        ("black_goblin",       3),
        ("steel_bat",          3),
        ("moth",               2),
        ("antler_stag",        2),
        ("giant_centipede",    2),
    ],
    "whisperwood_deep": [
        ("wolf",              14),
        ("werewolf",          12),
        ("ghoul",             12),
        ("ghost",             10),
        ("ochu",              10),
        ("harpy",              8),
        ("wind_serpent",       7),
        ("treant",             5),
        ("owlbear",            8),
        ("bugbear",            7),
        ("displacer_beast",    6),
        ("gnoll_hunter",       6),
        ("manticore",          5),
        ("wyvern",             5),
        ("bulette",            4),
        ("malboro",            4),
        ("ettercap",           4),
        ("chimera_dd",         3),
        ("hook_horror",        3),
        ("umber_hulk",         3),
        ("grimlock",           3),
        ("troglodyte",         3),
        ("zu_ff",              2),
        ("coeurl",             6),
        ("basilisk",           5),
        ("bomb",               4),
        ("gnoll",              4),
        ("ogre",               3),
        ("stroper",            5),
        ("bloom_creeper",      5),
        ("pink_puff",          4),
        ("frost_wolf",         4),
        ("lamia",              4),
        ("dhorme_chimera",     3),
        ("abductor",           3),
        ("cray_claw",          3),
        ("mini_satana",        3),
        ("magic_pot",          2),
        ("reflect_mage",       2),
        ("alchemist",          2),
        ("jura_aevis",         2),
        ("archaeoaevis",       2),
        ("killer_mantis",      2),
        ("minotaur",           2),
        ("birostris",          2),
        ("veiled_stalker",     2),
        ("behemoth",           2),
        ("antlion",            2),
        ("griffon",            2),
        ("naga",               2),
        ("drake",              2),
        ("gelatinous_cube",    2),
        ("serra_angel",        2),
        ("craw_wurm",          2),
        ("cactuar",            2),
        ("harpy_dd",           2),
    ],
    "aeridor_ruins": [
        ("skeleton",          12),
        ("soldier",           12),
        ("gargoyle",          10),
        ("golem",              8),
        ("dark_wizard",        8),
        ("skull_knight",       8),
        ("crystelle",          7),
        ("dark_knight",        7),
        ("tonberry",           6),
        ("lich",               4),
        ("beholder",           5),
        ("mind_flayer",        5),
        ("iron_giant_ff",      4),
        ("rakshasa",           4),
        ("bone_devil",         4),
        ("drider",             4),
        ("death_tyrant",       3),
        ("storm_giant",        3),
        ("balor_dd",           2),
        ("marilith",           2),
        ("glabrezu",           2),
        ("hezrou",             2),
        ("vrock",              2),
        ("dullahan",           5),
        ("mindflayer",         4),
        ("spectre",            4),
        ("clay_golem",         3),
        ("spectral_knight",    2),
        ("vecna_lich_god",     1),
        ("acererak",           1),
        ("chaos_ff1",          1),
        ("exdeath_ff5",        1),
        ("crew_dust",          4),
        ("iron_giant",         4),
        ("magic_dragon",       3),
        ("titan",              3),
        ("page_256",           3),
        ("soil_ghoul",         3),
        ("dragon",             3),
        ("adamantoise",        3),
        ("omega",              2),
        ("shinryu",            2),
        ("exdeath_tree",       2),
        ("azulmagia",          2),
        ("necrophobe",         2),
        ("gilgamesh",          2),
        ("apocalypse",         2),
        ("great_behemoth",     2),
        ("shadow_lich",        2),
        ("atomos",             2),
        ("grenade",            2),
        ("wyrm",               2),
        ("death_claw",         2),
        ("king_behemoth",      2),
        ("red_dragon",         1),
        ("frost_dragon",       1),
        ("iron_golem",         1),
        ("hydra",              1),
        ("dark_rider",         1),
        ("cave_crawler",       1),
        ("rust_monster",       1),
        ("tiamat_avatar",      1),
        ("nicol_bolas_echo",   1),
        ("bahamut_ff",         1),
        ("shivan_dragon",      1),
        ("sea_serpent_ff",     1),
        ("gorgon_dd",          1),
        ("air_elemental",      1),
        ("ancient_red_dragon", 1),
        ("tarrasque",          1),
        ("kraken_dd",          1),
    ],
    "trade_road": [
        ("goblin",            25),
        ("goblin_guard",      15),
        ("bandit",            20),
        ("wolf",              12),
        ("cockatrice",         5),
        ("kobold",            12),
        ("mudbrawler",        10),
        ("xvart",              8),
        ("kenku",              7),
        ("lizardfolk_dd",      6),
        ("goblin_guide",       5),
        ("orc_pawn",           8),
        ("orc_centurion",      5),
        ("gnoll",              4),
        ("pugil",              3),
        ("sand_angler",        3),
        ("gigas",              5),
        ("lizardman",          4),
        ("sea_snake",          4),
        ("snow_bandit",        3),
        ("earth_bear",         3),
        ("hill_gigas",         3),
        ("fire_gigas",         3),
        ("thri_kreen",         2),
        ("medusa",             2),
        ("troll",              2),
    ],
    "whisperwood_deep_night": [
        ("ghost",             20),
        ("ghoul",             15),
        ("nachtmahr",         15),
        ("shadow_dancer",     12),
        ("werewolf",          12),
        ("lich",               5),
        ("vampire_nighthawk",  8),
        ("nightmare_mtg",      7),
        ("death_knight_dd",    5),
        ("demogorgon_echo",    2),
        ("orcus_aspect",       2),
        ("grazzt_avatar",      2),
        ("juiblex_shadow",     2),
        ("hand_axe_goblin",    3),
        ("skeleton_archer",    3),
        ("moldwynd",           4),
        ("wight",              5),
        ("spectre",            5),
        ("vampire_lord",       3),
        ("ghast",              5),
        ("elder_treant",       2),
        ("tonberry_king",      2),
        ("zeromus_ff4",        1),
        ("lord_soth",          1),
        ("shinryu_ff5",        1),
        ("omega_ff5",          1),
        ("kefka_ascended",     1),
        ("sephiroth_echo",     1),
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