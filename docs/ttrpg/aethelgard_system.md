# ⚔️ Aethelgard — System Reference & Player Manual
*Build 0.5.0 · November 9, 2026 — Progression & Economy Pass*

> *"Oakhaven was built on the bones of Aeridor. Everything here is built on something older."*

---

## System Architecture

This document serves dual purposes:
1. **For LLM/developer context** — file map, data flow, and how systems connect
2. **For players** — game mechanics, commands, and reference tables

### Project File Map

```
utils/commands/rpg_handler.py      ← Main command router, UI views, combat flow, all !rpg commands
utils/ttrpg/
├── alchemy.py                     ← Recipes, brewing logic, ingredient discovery
├── calendar.py                    ← In-game calendar, seasons, special day buffs
├── character_manager.py           ← Character sheet CRUD (load/save to memory/ttrpg/characters/)
├── class_advancement.py           ← ADVANCED_CLASSES, TITLES, get_title(), apply_advancement()
├── combat_engine.py               ← Deterministic combat resolution, damage calc, streak tracking
├── dice_engine.py                 ← d20/dN rolling, stat checks, formatted breakdown strings
├── dungeon.py                     ← Procedural 5×5 maze gen, room types, boss pools, map render
├── encounter_tables.py            ← Per-location monster encounter weights and event chances
├── equipment_registry.py          ← WEAPONS, ARMOR, CONSUMABLES, HEADGEAR, BOOTS, ACCESSORIES
├── forest_events.py               ← Forest event handlers and the dispatcher (Sylvan Sprites, Tonberry, etc.)
├── forest_events_rare.py          ← Lore, rare, night-only and legendary forest events
├── lore.py                        ← The Lore Codex: pages, sets, set rewards, `!rpg lore`
├── look_targets.py                ← Hardcoded "look at <thing>" flavor text per location
├── loot_tables.py                 ← Tier-aware loot drops from monsters and dungeon chests
├── micro_events.py                ← Overworld traveling events, weather discoveries, and streak rewards
├── monster_registry.py            ← Full bestiary: 369 monsters across 7 tiers (44 boss-tier)
├── noon_events.py                 ← Noon events that drive rare content (Starfall, Archivist, Migration, Hollow Sun, Ghost Caravan)
├── npc_registry.py                ← NPC definitions: Elara, Hemlock, Mira, Guard, Maren, Bard
├── progression.py                 ← XP thresholds, level-up, daily hunt reset, condition expiry
├── quest_registry.py              ← Quest definitions and lookup helpers
├── rare_spawns.py                 ← Rare monster variants (Gilded, Elder, Pale, Whispering, Resonant)
├── rpg_prompt_builder.py          ← Ground-truth blocks injected into Kaia's LLM prompts
├── rpg_ui.py                      ← Shared UI components (buttons, selects)
├── session_manager.py             ← Multi-player session tracking
├── shop.py                        ← Buy/sell logic with CHA modifiers
├── world.py                       ← LOCATION_DATA, resolve_location() alias matching
└── world_state.py                 ← Global world state (weather, reputation, events log)

utils/core/background_tasks.py     ← Dawn reset, noon events (raids, caravans, bard performance)
docs/ttrpg/aethelgard_system.md    ← This file
knowledge_base/books/              ← Lore documents (aethelgard_manual.md, aethelgard_world-lore.md)
memory/ttrpg/characters/           ← Per-user JSON character sheets
memory/ttrpg/dungeons/             ← Per-user active dungeon state
memory/ttrpg/world_events.json     ← Rolling log of world events
```

### Data Flow

1. **Player sends `!rpg <command>`** → the RPG router dispatches to the relevant handler.
2. **Handler loads the sheet** via `character_manager.load(uid)` → JSON from `memory/ttrpg/characters/`.
   Character and housing loads verify the embedded owner matches the requested filename; legacy
   records without an owner ID adopt the filename, while mismatches fail closed before gameplay
   mutation.
3. **Game logic** runs deterministically (dice_engine, combat_engine, shop, etc.).
4. **Shared world reads** use `world_state.load_world_state()`, which returns an expiry-normalized view and does not write.
5. **World-only updates** use `world_state.update_world_state(mutator)`; the transaction lock covers fresh load, mutation, and atomic save.
6. **Character + world actions** use `world_state.mutate_world_state()` so resource costs/rewards and global state share one recovery journal. Combat, housing, dungeon, and Spine use their corresponding outcome/resource journals.

A pending shared-world journal is single-owner. Recovery verifies that its non-empty `user_id` matches the saved `character_sheet.user_id` before writing either snapshot. A mismatch fails closed and leaves the journal untouched for diagnosis; it must never replay one player's snapshot into another player's character file.

7. **Kaia narrates** via `rpg_prompt_builder.py` → GPU-guarded LLM call → flavor text embed.
8. **Sheet/UI state** is persisted before the Discord view is returned.

Bulk character and housing discovery uses per-file scan reports. Readable players remain available
when one record is damaged, but the report identifies the skipped path and owner ID; leaderboards
and player lists built from partial results must say that the result may be incomplete.

Do not build an async read-modify-write by loading a complete world-state snapshot and later passing it to `async_save_world_state()`: the final write lock cannot make the earlier read fresh. Synchronous `save_world_state()` is reserved for isolated tests/bootstrap.

---

## The World

Aethelgard is a persistent world running at all times. Players drop in and pick up where they left off. All characters share one world — Gil, XP, equipment, and location persist across sessions.

The game runs in:
- **`#aethelgard`** — Broadcast channel for dawn announcements and world events
- **`#aethelgard-tales`** — Forum channel where players create threads to play

---

## Character Creation

```
!rpg new <Name> <Race> <Class>
```

Stats rolled with 4d6 drop lowest, six times. The best roll goes to the class's attack stat and the
next best to CON; the other four keep the order they were rolled in
(`rpg_character_creation_handler.assign_rolls`). Level-1 HP is **twice the class hit die plus the CON
modifier** (`character_manager.starting_hp`): a Warrior with CON 14 starts on 22, a Mage on 14. Type
`!rpg` to open the HUD.

### Races

| Race | Bonuses |
|:--|:--|
| **Human** | +1 to all stats |
| **Elf** | DEX +2, INT +1, WIS +1 |
| **Silvani** | DEX +2, WIS +2 |
| **Dwarf** | CON +2, STR +1 |
| **Glimmerkin** | CHA +2, INT +1, DEX +1 |
| **Veiled** | INT +2, CHA +2 |

### Classes

| Class | Attack Stat | HP/Level | Flavor |
|:--|:--|:--|:--|
| 🗡️ **Warrior** | STR | 8 | Heaviest hits, highest HP |
| 🏹 **Ranger** | DEX | 7 | Consistent damage, forest-attuned |
| 🔮 **Mage** | INT | 5 | Glass cannon, INT drives everything |
| 🗝️ **Rogue** | DEX | 5 | Crits on 19-20 |
| ✨ **Cleric** | WIS | 6 | Healing bonus on consumables |

---

## Title System

Every class earns titles at milestone levels. The HUD displays as `(Title) Class` — e.g. `(Channeler) Mage`.

### Base Class Titles

| Class | L1 | L3 | L5 | L7 | L9 |
|:--|:--|:--|:--|:--|:--|
| Warrior | Grunt | Soldier | Veteran | Warlord | Champion |
| Ranger | Scout | Tracker | Pathfinder | Outrider | Stalker |
| Mage | Apprentice | Channeler | Invoker | Arcanist | Magister |
| Rogue | Cutpurse | Shadow | Blade | Phantom | Wraith |
| Cleric | Novice | Acolyte | Cleric | Devout | Saint |

### Advanced Class Titles (L5–L10)

Each advanced class has its own title track (see `class_advancement.py` for full list).

---

## Class Advancement (Level 5)

At level 5, players choose to advance or stay:

| Base | Option A | Option B | Stay (base class bonuses) |
|:--|:--|:--|:--|
| Warrior | Paladin | Shadowknight | +5 HP, +1 ATK, +1 DEF |
| Ranger | Hunter | Warden | +5 HP, +1 ATK, +1 DEF |
| Mage | Wizard | Necromancer | +5 HP, +1 ATK, mana_regen |
| Rogue | Shadowblade | Trickster | +5 HP, +1 ATK, crit_chance_bonus |
| Cleric | High Priest | Shaman | +5 HP, +1 DEF, heal_on_kill |

Advancement is **optional**. Staying grants modest stat bonuses instead of hybrid abilities.

---

## Locations & Navigation

All navigation is button-driven. Players use the HUD buttons or `!rpg go <location>`.

### Location Map
```
                  [Spine Mega-Dungeon (Dungeon-only)]
                         |
                    [Grimstone (Lore-only)]
                         |
              [Trade Road] ──── [Aeridor Ruins]
             /            \
        [Caravan]    [Tricklebrook Pond]
                         |
                    [OAKHAVEN] ──── [Housing District]
                   /    |    \
          [Stone  ] [Hemlock's] [Shrine →  Maren's Hut]
           Hearth]  [Store]
                         |
                  [Whisperwood Edge]  ← lvl 1+
                         |
              [Whisperwood Deep]  ← lvl 4+
```

### Location Services

| Location | Key Services |
|:--|:--|
| **Oakhaven** | Look, map, calendar, weather, notices, quests, deliver, `donate` (town walls) |
| **Stone Hearth** | Rest (5g at level 1, +2g a level: 33g at 15), drink (+3 temp HP, 2g), gamble (10g; net winnings capped at 100g a day), rumor, talk NPCs |
| **Hemlock's Store** | Shop: Tier 1 and Tier 2 gear (the menu lists what your class can wear), bandages, herbs, tonics, standard potions, torches. Buy, sell (a fifth of value; 25% at 50 reputation, 30% at 100), `enhance` (+1 to +5), inventory, talk |
| **Shrine** | Pray (Blessed), offer Gil→XP, fountain (full heal 1/day), look flame/altar |
| **Watchtower** | Scout (1/day), talk guard |
| **Maren's Hut** | Brew alchemy recipes, talk Maren |
| **Bank** | Deposit, withdraw (protects Gil from blackout loss). Only here, or at home with an Ironbound Vault Chest; the balance can be checked anywhere. |
| **Housing District** | Buy a home, `!rpg home` (Farming, Pets, Decorate) |
| **Tricklebrook Pond** | `!rpg fish`, `!rpg fish_shop` (Buy bait/poles) |
| **Grimstone (Lore-only)** | Unimplemented overworld location |
| **The Rusty Pick (Lore-only)** | Unimplemented inn (Lore-only) |
| **Pell's Depot (Lore-only)** | Unimplemented store (Lore-only) |
| **Caravan** | Only present during certain noon events. Tier 3 gear (one piece a visit), standard and hi-potions, lightstones. |
| **Hunting zones** | Hunt (1 of 5 daily hunts), look |

---

## Combat

Fully automatic. Player never touches dice.

**Attack:** `d20 + class_attack_mod + weapon_bonus vs monster_DEF`
**Damage:** `weapon_die + class_attack_mod`
**Player DEF:** `10 + DEX_mod + effective_gear_def` (Max `Level * 1.5 + 12`). Gear DEF is soft-capped: `min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2`.
**Monster ATK:** Uses actual monster ATK stat. Overworld scaling uses logarithmic dampening (max 1.35x based on distance), then a cap of `level * 1.5 + 2`.
**Overworld monster HP:** zone distance × base HP, capped at `14 + 7 * level` (`encounter_tables.overworld_hp_cap`). Above the easy tier every tier shares one HP range (75–100 base), so without the cap a level-4 player met 92-HP mediums.
**Crit (nat 20):** Damage dice doubled
**Fumble (nat 1):** Auto-miss

### Overworld Encounter Ownership

Overworld monsters are personal encounters, not shared party fights. Only the player who spawned a monster may attack it, and only while at the RPG location recorded when it spawned. This includes monsters hooked while fishing and blockade raid encounters. Same-channel and same-location players cannot assist another player's monster yet: the game does not currently track party membership, contributions, or fair XP, gil, drop, quest-credit, and streak shares. A player who moves away must return to the encounter location or use `!rpg flee` to abandon the old encounter. Older monsters without a recorded origin location are not attackable; flee and start a new hunt.

### Weapon Procs
Select T3+ weapons possess inherent elemental procs. These trigger independently on standard hits (10% chance) and critical hits (50% chance). They scale in extra damage from 1d4 to 1d12 based on weapon tier, and can trigger simultaneously alongside Class Procs.

**Order of a hit.** Base roll + flat bonuses, then the class proc and the weapon proc are added, then advanced-class damage bonuses — so Shadowknight lifesteal (Dark Embrace) drains from the complete hit. Monster HP is reduced once by that total. Heals (class proc, lifesteal, drain weapons) apply after the damage. Kill-only advanced effects run after the duel non-lethal guard, before the monster's counterattack.

**Dice notation** (`dice_engine.roll`) accepts 1–20 dice of 2–100 sides and a modifier of at most ±50.

### Inventory Capacity Cap
Each character may carry up to **100 unique item types**. Duplicate copies of an item already in the inventory do not use additional capacity; stack quantity is otherwise unlimited by this rule. A purchase, brew, harvest, or loot grant is allowed when it adds no new item type or when a new type keeps the total at 100 or fewer. A grant that would introduce a 101st unique type is refused; combat drops are left behind with an `🎒 [Inventory Full]` message, and full-bag crops remain on their plots until the player makes room. Player-facing event, quest, fishing, and dungeon rewards that cannot fit are preserved in **Moogle Mail**; claim them after making room. Mail claims are partial: attached Gil can be collected immediately while an item that does not fit stays in the mailbox. Buyback, equipment changes, and Starter Kit opening are refused without consuming currency or items when the required inventory change would exceed the cap.

### Player vs Player (Duels)
Players can challenge each other to non-lethal combat using `!rpg duel @user`. Upon acceptance, the duel resolves automatically until one player is reduced to 1 HP. No XP or Gil is lost.

### Combat Streak
Consecutive wins → +1 to-hit, Gil multiplier on drops. Reset on flee/blackout.

### Blackout (HP → 0)
- Lose 10% XP, 5% Gil
- Wake at Shrine with 1 HP
- Kaia narrates recovery

---

## Hunting & Forest Events

Each hunt costs 1 of 5 daily hunts. Hunts may trigger a **forest event** instead of a monster. **Events are free — they do not consume a daily hunt.** The player still gets their full 5 hunts for combat XP. To prevent repeated free rerolls, each player has up to **5 forest-event roll attempts per day**; attempts count whether or not an event triggers and reset at the same daily boundary as hunts. Once those attempts are used, hunts proceed directly to monster encounters. This separate limit does not consume hunt stamina. When a damaging event reduces a character to 0 HP, it uses the normal overworld blackout: the character wakes at the Shrine with 1 HP, loses 10% of current XP and 5% of current Gil, gains a death, loses their hunt streak, and the outing is closed. The location percentages in the table are base chances; temporary world-state forest-event bonuses and weather modifiers are added to that base when the roll is made.

| Location | Event Chance | Rec. Level |
|:--|:--|:--|
| Whisperwood Edge | 20% | 1+ |
| Trade Road | 18% | 2+ |
| Whisperwood Deep | 15% | 4+ |
| Aeridor Ruins | 10% | 7+ |

**What a hunt can meet** depends on the player's level, filtered from the zone's table
(`encounter_tables.TIER_WINDOWS`). One bound moves at a time, and never on a level where a zone opens:

| Level | Tiers |
|:--|:--|
| 1–4 | trivial – easy |
| 5 | trivial – medium |
| 6–7 | easy – medium |
| 8–9 | easy – hard |
| 10 | medium – hard |
| 11–12 | medium – deadly |
| 13 | hard – deadly |
| 14–15 | hard – boss |

At night a quarter of hunts shift up a tier.

**Drops.** A kill rolls the gear table 35% of the time and the consumable table half the time
(`loot_tables.roll_kill_drops`); an ordinary dungeon mob rolls gear 30% of the time. The tables alone
dropped gear on 74–100% of kills, and selling it was three quarters of all income.

### Forest Events (44 total: 31 common, 10 rare or lore, 3 legendary)

| Event | Key Mechanic |
|:--|:--|
| ✨ Sylvan Sprites | Heal 4-11 HP |
| 🎪 Moogle Sighting | 10-30 Gil or +1 hunt |
| 🌿 Injured Silvani | WIS check → herbs + XP |
| 🧙 Old Man's Riddle | INT check DC 8 → XP/Gil/Sharp Mind |
| 🐦 Chocobo Tracks | +1 hunt, +12 XP |
| 💎 Aeridor Fragment | Crystal shard (sell 30g) |
| 🍄 Gilded Mushroom | Rare ingredient (sell to Hemlock) |
| 👁️ Veiled Elder | Class-specific buff until next combat |
| 🔪 Timid Tonberry | 60-100 Gil / knife / clean escape |
| 📬 Mognet Delivery | Letter → deliver in Oakhaven for reward |
| 🔮 Crystal Resonance | INT check → big XP or HP damage |
| 🌳 Whisper in Bark | WIS check → Tree Memory buff |
| 🌵 Cactuar Sighting | DEX DC 18 → 200 XP, 120 Gil |
| 🏕️ Abandoned Camp | Random supplies + lore |
| 🗿 Strange Statue | INT/WIS → Aeridorian Attunement or trap |
| 🔮 Echo of Aeridor | Passive XP (scales with level) |
| 💤 Dream Walker | Silvani heals player passively |
| 🕯️ Twin Wisps | Follow both/one/neither → reward/penalty/ward |
| 🧭 Lost Merchant | 20-60 Gil reward |
| 🪙 Ancient Coin | Lucky Charm item |
| 📋 Missing Person Found | Escort missing villager back → +100 XP, +100 Gil, +10 Reputation |
| 🔵 The Blue Flame's Echo | WIS check DC 9 → Sharp Mind or -3 HP |
| 🎴 A Stranger's Coin | 15% Aeridor Crystal Shard OR 15-35 Gil |
| 🌲 The Moved Boundary | XP reward + border shift lore |
| 👀 The Watching Silvani | CHA check DC 8 → 20-40 Gil OR XP only |
| 🌱 Early Bloom | Gather Silvermoss + XP |
| 🛒 Wagon Tracks | 50% Gil OR 50% Sharp Mind |
| 🏮 The Unclaimed Lantern | DEX check DC 10 → Torch OR -4 HP |
| 👂 The Silent Chorus | INT check DC 9 → scaled XP reward |
| 🍯 Sap-Slicked Roots | Gather Honey Sap + XP (30% slip/HP loss) |
| 🦇 The Uninvited Guest | WIS check DC 12 → Wisp Ward + 30 Gil OR -6 HP |
| 🧭 The Cartographer's Cairn | Wayfarer's Notes page, +15 XP (25 Gil once the set is complete) |
| ✉️ The Fallen Courier | Aeridor Codex page, +20 XP (40 Gil once complete) |
| 🎵 The Songstone | WIS DC 11 → Songs of the Silvani page + 20 XP, OR -4 HP |
| 🏮 The Lantern Shrine | Leave 10 Gil → Tonberry Ledger page + 20 XP (nothing taken if you have under 10) |
| 🪞 The Mirror Pool | 50%: Mirror Resolve (+2 DMG next fight) + 25 XP, OR -6 HP + 20 XP |
| 🎪 The Stall That Wasn't There | A gem: Pearl 60% / Opal 30% / Black Pearl 10%, +10 XP |
| 🐦‍⬛ Seven Crows | First time: an Oddities page and *Lucky*; +15 XP |
| 👴 Old Man Hemlock? | A Hi-Potion, +20 XP; first time an Oddities page |
| 🌠 A Fallen Star | **Night only** (any time during Starfall): Aeridor Crystal Shard, +30 XP, Oddities page; announced in #aethelgard |
| 🌑 The Quiet Hunter | **Night only**, Deep: DEX DC 12 → Shadow Step + 25 XP, OR -8 HP |
| 🚪 The Door in the Oak | **Legendary**: full HP, a hunt returned, +50 XP, Oddities page; announced |
| 🪨 The Tablet That Knew Your Name | **Legendary**: +77 XP, +77 Gil, Oddities page; announced |
| 🦌 The Gilded Stag | **Legendary**: a Diamond, +100 XP; announced |

### Rare Encounters

- **Legendary events** are rolled before the location table: 1 in 120 forest events
  (`forest_events_rare.LEGENDARY_ONE_IN`), only where each one lives (the Door: Edge and Deep;
  the Tablet: Ruins and Deep; the Stag: Edge, Deep and Trade Road).
- **Night-only events** (Fallen Star, Quiet Hunter) roll between 18:00 and 06:00. Starfall lets
  the Fallen Star fall by day too, at three times its weight; the Archivist doubles the four lore events.
- **Rare variants:** 1 overworld spawn in 40 (`rare_spawns.RARE_ONE_IN`; 1 in 10 during the
  Gilded Migration or the Hollow Sun) is a variant of the creature rolled. It keeps its key (quest
  kills still count) and its ATK; quest-boosted spawns and bosses never are one.

| Variant | Where / when | HP | XP | Gil | Its own drop |
|:--|:--|:--|:--|:--|:--|
| 🪙 Gilded | anywhere | ×1.3 | ×2 | ×5 | a gem: Opal 50% / Black Pearl 30% / Star Ruby 15% / Diamond 5% |
| 🌳 Elder | anywhere | ×1.6 | ×3 | ×2 | a gear drop rolled one tier up |
| 🌫️ Pale | night only | ×1.4 | ×2.5 | ×2 | a lore page from any set |
| 🍃 Whispering | Whisperwood Edge/Deep | ×1.4 | ×2.5 | ×2 | a Songs of the Silvani page |
| 💎 Resonant | Aeridor Ruins | ×1.4 | ×2.5 | ×2.5 | an Aeridor Codex page |

A lore variant whose set is already complete carries a gem instead. Each kill is announced in
#aethelgard ("✨ Rare Hunt").

### The Lore Codex

`!rpg lore` lists every page (`???` for one not yet found); `!rpg lore <n>` reads one. Pages live on
the sheet (`lore_pages`); a set completed for the first time pays once (`lore_sets_done`) and is
announced in #aethelgard.

| Set | Pages | Found in | Completion reward |
|:--|:--|:--|:--|
| 💎 The Aeridor Codex | 6 | Fallen Courier, Resonant variants, Pale variants | 300 Gil, 250 XP, Star Ruby |
| 🍃 Songs of the Silvani | 4 | Songstone, Whispering variants, Pale variants | 200 Gil, 200 XP, Moonwater |
| 🏮 The Tonberry Ledger | 3 | Lantern Shrine, Pale variants | 250 Gil, 150 XP, Black Pearl |
| 🧭 Wayfarer's Notes | 3 | Cartographer's Cairn, Pale variants | 150 Gil, 150 XP, Opal |
| 🌀 Oddities & Rumours | 5 | Seven Crows, Old Man Hemlock?, Fallen Star, the Door, the Tablet | 500 Gil, 300 XP, Blue Diamond |

---

## CHA Stat Effects

| System | Effect |
|:--|:--|
| **Shop (buy)** | -2% per CHA mod (max -10%) |
| **Shop (sell)** | +2% per CHA mod (max +10%) |
| **NPC dialogue** | LLM instructed to be warmer/colder based on CHA |

CHA modifier = `(CHA - 10) // 2` (standard TTRPG formula).

---

## Dungeons

Procedurally generated 5×5 grid, 9-12 rooms. Entered via button at hunting locations.

### The Spine of the World
A massive 77-floor mega-dungeon — the Ironvein Deep — entered with `!rpg dungeon` from the Aeridor Ruins (Grimstone, the town once planned in front of it, was cut in May 2026). Unlike procedural dungeons, the Spine features a fixed, hand-crafted 24x24 layout with intricate floor connectivity, static encounters, dynamic hallway traps, and unique bosses. It features checkpoint lifts every 5 floors (a stop unlocks when the player reaches that floor: beating floor N's stair guardian opens N + 1) and progressive floor-based monster scaling (`mob_hp_cap = 80 + floor_num * 3` and `mob_atk_cap = 12 + floor_num // 5`; mobs are scaled as difficulty 2 on floors 1–19, 3 from 20, 4 from 40, 5 from 60, `dungeon.spine_scaling_difficulty`). Every mob, procedural or Spine, is also bounded by the player's level: HP at 1.15× (1.3× in the Spine) the overworld cap, ATK at `level * 1.5 + 2` (`dungeon.scale_dungeon_mob`).

A procedural dungeon's difficulty is 1 to level 4, 2 from 5, 3 from 8, 4 from 11 (`dungeon.dungeon_difficulty`): a level after each zone opens, so a new zone and a harder dungeon never arrive together.

### Stair Guardian Progression

The 77 stair guardians are **floor-scaled progression checks**, not fixed-stat story bosses. The
bestiary entries remain the narrative/stat templates; the stair path scales a deep copy for that
floor and never changes the shared registry. The ordinary Spine room path uses difficulty-5
scaling (1.6x base stats) and the documented HP/ATK caps. Guardian instances sit above that curve:

- **HP:** at least 1.2x the floor HP cap (`ceil((80 + floor_num * 3) * 1.2)`), and at least
  one point above the same monster's ordinary difficulty-scaled room HP.
- **ATK:** at least two points above the ordinary floor attack cap and the same monster's
  difficulty-scaled attack. The floor cap uses the current level-15 maximum (`int(15 * 1.5 + 2)`)
  before adding the guardian margin.
- **DEF:** `20 + floor_num // 8`, rising from 20 on floor 1 to 29 on floor 77. This is above
  the ordinary difficulty-scaled DEF range of the registered guardians.
- **Special mechanic — Resonance Ward:** no ward on floors 1–14; it absorbs 5% of incoming
  player damage on floors 15–29, then gains another 5 percentage points at floors 30, 45, 60,
  and 75, reaching 25% on floors 75–77. The ward is stored on the individual guardian instance
  and applied by combat resolution; ordinary monsters are unaffected.

At floor 77, **The Mountain Heart** is 374 HP / 26 ATK / 29 DEF with a 25% Resonance Ward,
compared with its ordinary difficulty-scaled room values of 160 HP / 19 ATK / 19 DEF. Other
campaign story bosses retain their existing encounter-specific rules (including player-level
scaling for procedural dungeon bosses); this floor curve applies only to named stair guardians.

### Room Types

| Type | Weight | Description |
|:--|:--|:--|
| Empty | 18 | Safe room |
| Monster | 45 | Auto-combat encounter |
| Treasure | 15 | Tier-scaled loot chest |
| Shrine | 8 | Heal point, may have secret quest seal |
| Trap | 14 | HP damage trap |
| Boss | 1/dungeon | Unique-named boss at farthest room |

**Every dungeon is guaranteed ≥1 shrine room.** If RNG doesn't roll one, an empty room converts.

### Secret Shrine (Quest)
Some shrine rooms contain a **sealed Aeridorian shrine** with a three-flame seal. Players who've studied the flame and altar at the Oakhaven Shrine (`look at the flame` and `look at the altar` both count) can interact.

### Boss Scaling & Encounters
Procedural dungeon boss HP and ATK use a **linear level multiplier** from `0.45x at L1` to `1.0x at L15`: `0.45 + (level - 1) * (0.55 / 14)`, with levels clamped to 1–15. The per-level HP and ATK caps are applied after scaling and remain separate balance limits. Boss DEF is not multiplied; it keeps its existing level adjustment, `max(8, base_DEF - max(0, 5 - level))`. Dungeon Boss ATK caps are tightly calibrated to ensure a ~50-55% hit rate.
**Boss Room Warning:** Entering a boss room triggers a narrative warning, allowing players a chance to retreat before engaging.

---

## Alchemy

Recipes are discovered by picking up ingredients. Brewed at Sister Maren's Hut.

| Recipe | Ingredients | Result |
|:--|:--|:--|
| Health Potion | Blood Thistle + Honey Sap | `potion_standard` (25 HP) |
| Hi-Potion | Blood Thistle + Silver Moss | `hi_potion` (20 HP) |
| Elixir | Silverleaf + Dire Root | `elixir` (30 HP) |
| Phoenix Brew | Silverleaf + Star Ruby | `phoenix_down` (50 HP) |
| Experience Tonic | Silverleaf + Emerald | `xp_tonic` (+25% XP) |
| Hunter's Draught | Dire Root + Topaz | `hunters_draught` (+1 Hunt) |
| Ironbark Tonic | Dire Root + Pearl | `ironbark_tonic` (+2 DEF) |
| Firebrew | Blood Thistle + Fire Opal | `firebrew` (+2 ATK) |
| Antidote | Silver Moss + Honey Sap | `antidote` (Cure poison) |
| Smoke Bomb | Blood Thistle + Topaz | `smoke_bomb` (Safely escape your own overworld encounter; no hunt stamina or XP/Gil loss) |
| Warding Salve | Silver Moss + Pearl | `warding_salve` (+2 DEF until combat ends) |
| Frenzy Draught | Blood Thistle + Star Ruby | `frenzy_draught` (+2 ATK until combat ends) |
| Moonwater | Silverleaf + Black Pearl | `moonwater` (Full HP restore) |

---

## Consumables

| Item | HP Restore | Price | Tier |
|:--|:--|:--|:--|
| Bandage | 5 | 6g | 1 |
| Healing Herb | 8 | 10g | 1 |
| Tonic | 15 | 20g | 2 |
| **Health Potion** (brewed) | **25** | 15g | 2 |
| Hi-Potion | 20 | 30g | 3 |
| Elixir | 30 | 50g | 4 |
| Phoenix Down | 50 | 80g | 4 |
| Antidote | — | 25g | 2 |
| Smoke Bomb | — | 30g | 2 |
| Warding Salve | — | 45g | 3 |
| Frenzy Draught | — | 50g | 3 |
| Moonwater | 150 (Full) | 150g | 4 |

Retired consumables: **Eye Drops** and **Trap Kit** are no longer sold, craftable, or usable. The current status system has no blindness condition and the dungeon system has no trap-placement mechanic. Existing copies remain in inventory and can still be sold to a merchant.

### Buff Potions & Utility (Crafted)
| Item | Effect |
|:--|:--|
| Experience Tonic | +25% XP on your next hunt / dungeon kill |
| Hunter's Draught | Instantly refunds 1 daily hunt upon use |
| Ironbark Tonic | Grants `Fortified` (+2 DEF for one entire combat encounter) |
| Firebrew | Grants `Embered` (+2 ATK for one entire combat encounter) |
| Smoke Bomb | Safely escape your own overworld encounter without spending a hunt or losing XP/Gil |
| Warding Salve | Grants `Fortified` (+2 DEF until combat ends) |
| Frenzy Draught | Grants `Embered` (+2 ATK until combat ends) |

---

## Endgame Gil Sinks

Two sinks stay worth paying for at the cap.

- **Hemlock's rework** (`!rpg enhance [slot]`, `utils/ttrpg/enhancement.py`): equipped gear goes
  +1 to +5. Each level costs half the item's value (at least 1,000g) times the level being bought —
  top gear to +5 is 150,000g. Armour, headgear, boots and accessories gain +1 DEF per level, through
  the gear soft-cap and the global DEF cap; weapons alternate +1 ATK and +1 damage. Levels belong to
  the item key, so they survive unequipping.
- **The town walls** (`!rpg donate <gil>` at the town square, `utils/ttrpg/town_projects.py`): gil
  pooled from everyone. At 250,000g the walls are reinforced for 7 days and every noon raid is fought
  with +2 DEF; a second project extends the week.

Shared one-time actions are serialized against the global world state. Pond purification is a single
server-wide claim: the first eligible player consumes one reagent and receives +50 XP / +15 town
reputation; later attempts see clear water and receive no reward. Town donations commit the player's
gil deduction together with the town fund, donor totals, and reinforcement expiry. If the process
stops between the two JSON writes, a durable journal replays both snapshots before the next character
load, so neither a paid donation nor a purification reward is lost or duplicated.

---


## Multi-file Persistence and Crash Recovery

Aethelgard's character sheets, housing, shared world state, and encounter data are separate JSON
records. When one gameplay action changes more than one record, it must use the journal belonging
to that resource rather than saving each file independently.

- **Character + housing, dungeon, or Spine:** `housing_transactions.commit_character_resource()` writes a per-player
  write-ahead journal containing both intended snapshots. It then saves the character and secondary
  resource, clearing the journal only after both writes succeed. The housing, dungeon, and Spine
  convenience wrappers use the same protocol. Housing actions covered include purchases, upgrades,
  crop planting and harvesting, blight treatment, pet adoption and feeding, furniture purchases,
  home training, and daily Mognet deliveries. Dungeon and Spine entry, room rewards, continuing
  combat rounds, and fleeing use the same journal when both the sheet and encounter snapshot change.
- **Character + shared world state:** pond purification, town donations, and the successful bandit-cache
  raid use `world_state.mutate_world_state()` so costs/rewards and global pond, town-fund, or shop
  inflation changes share one durable journal. A Bandit Captain victory stores its blockade-clearing
  effect in the pending combat outcome and replays that idempotent world mutation before clearing the
  encounter.
- **Combat outcomes:** a character-sheet pending-outcome record is written before a dungeon, Spine,
  or overworld encounter is changed. The next combat action replays any unfinished operation
  before resolving another round. This covers terminal rewards/penalties, ongoing overworld and
  dungeon combat rounds, ordinary flee, and Smoke Bomb escape. Replays are idempotent; unknown
  journal kinds are retained rather than silently discarded.
- **Shared overworld sessions:** a channel session contains encounters for multiple players. A
  player's recovery must therefore patch or remove only that player's monster IDs. It must not
  restore a stale copy of the whole channel session. Combat-log entries carry an outcome ID so
  recovery can append a round once, even if the session write succeeded and journal cleanup did not.
- **Fishing monster hooks:** the stable cast ID is recorded in a shared-session hook receipt and on
  the spawned monster before the character sheet records the consumed cast ID. A retry reuses the
  receipt and debits bait only once; the per-character consumed-cast marker prevents a delayed retry
  from respawning an encounter after session cleanup.

The hunt entry flow deliberately reserves hunt stamina before rolling/spawning monsters. That is a
one-way reservation: a failure after the debit does not create a free reroll. These journals are
write-ahead records, not substitutes for per-file atomic writers or action locks. A successful
operation clears its journal only after all required writes complete; if a write fails, the next
recovery replays the saved snapshots or targeted mutation. RPG unit tests inject failures at both
sides of these boundaries and verify repeat recovery does not duplicate rewards, costs, or shared
session changes.

## Housing System

Players can purchase a home in the **Housing District** (`!rpg go housing_district`): a Hut for 1,000 Gil, then a Cottage (5,000), a Longhouse (15,000) and the Keep (40,000). Upgrading unlocks more options. Access your home menu using `!rpg home`.

### Farming
Grow crops in your farming plots. Seeds are bought from Hemlock or found. Crops grow over time/interactions, yielding items and cooking ingredients.

### Pets
Adopt pets to live in your home from Pip the Pet Vendor in the Housing District. Pets require daily feeding (paid in gold based on food type) and provide powerful passive bonuses when well-fed.

Daily farm/pet resets are applied when the character is loaded for the new day, not when housing is read. The reset is committed with the character sheet through the housing recovery journal; House Moogle delivery counters and mailbox rewards are one atomic transaction. A newly created home starts with the current reset date so its first pet feeding is not cleared by a later read that same day.
- **Oakhaven Cat**: +5% Gil from kills when fed. (Food: Fish, cost 5g)
- **Chocobo Chick**: +1 hunt per day when fed. (Food: Gysahl Greens, cost 8g)
- **Tiny Tonberry**: +2 to all combat rolls when fed. (Food: Lantern Oil, cost 15g)
- **Sylvan Sprite**: Restores 3 HP after every combat when fed. (Food: Honey Sap, cost 5g)
- **House Moogle**: Delivers one random item per week from Mognet network when fed. (Food: Kupo Nut, cost 20g)
- **Miniature Construct**: +3 DEF passively while fed. (Food: Aeridor Shard, cost 30g)
- **Iron Pup**: +1 DEF, and 5% chance to find extra loot chests in dungeons when fed. (Food: Iron Plating, cost 15g)
- **Tomb Bat**: +10% Gil from dungeon kills when fed. (Food: Blood Thistle, cost 10g)
- **Wisp Lantern**: +5% XP boost when fed. (Food: Honey Sap, cost 5g)

### Furniture
Decorate your house to gain passive bonuses (e.g., Alchemy Workbench enables `!rpg brew` from home, Weapon Rack gives +1 ATK locally, Bed speeds up resting).

---

## Fishing System

Travel to **Tricklebrook Pond** (`!rpg go tricklebrook_pond`) to fish. Open the UI with `!rpg fish`.
1. **Poles & Bait:** Buy from the Fish Shop. Better poles have faster bite times and higher durability. Specific baits attract specific fish.
2. **Casting & Reeling:** Cast your line. When a fish bites, an interactive mini-game tests your timing and click speed.
3. **Selling:** Fish can be sold for Gil or sometimes used in recipes.

---

## Conditions & Buffs

All temporary conditions are cleared on daily reset (midnight). Only `Blessed` and `mognet_pending` persist.

| Condition | Source | Effect |
|:--|:--|:--|
| Blessed | Shrine prayer | +2 to all rolls (consumed after 1 combat) |
| Ale Warmth | Stone Hearth drink | +3 temp HP (cleared on rest or day reset) |
| XP Boosted | Experience Tonic | +25% XP on the next combat kill |
| Fortified | Ironbark Tonic / Warding Salve | +2 DEF applied for one entire combat encounter |
| Embered | Firebrew / Frenzy Draught | +2 ATK applied for one entire combat encounter |
| Sharp Mind | Old Man's Riddle | +1 ATK for the next fight |
| Battle Focus | Veiled Elder (Warrior) | +1 ATK for the next fight |
| Forest Sight | Veiled Elder (Ranger) | +1 ATK for the next fight |
| Resonance Link | Veiled Elder (Mage) | +2 damage for the next fight |
| Shadow Step | Veiled Elder (Rogue), Quiet Hunter | +2 ATK for the next fight |
| Divine Clarity | Veiled Elder (Cleric) | +2 damage for the next fight |
| Tree Memory | Whisper in Bark | -2 damage from natural creatures (not undead or constructs) for one fight |
| Wisp Ward | Twin Wisps (ignored both), Uninvited Guest | +1 DEF for one fight |
| Aeridorian Attunement | Strange Statue | +1 ATK in the Aeridor Ruins until the daily reset |
| Mirror Resolve | Mirror Pool | +2 damage for one fight |
| Lucky | Seven Crows, Lucky Charm | +1 to hit on the next attack |

---

## NPCs

| NPC | Location | Role |
|:--|:--|:--|
| Elder Elara | Oakhaven | Quest giver, town leader |
| Old Man Hemlock | Hemlock's Store | Merchant |
| Mira | Stone Hearth | Innkeeper |
| The Hooded Figure | Stone Hearth | Mystery, lore hints |
| Watchtower Guard | Watchtower | Scout info, quest giver |
| Sister Maren | Herbalist's Hut | Alchemy, herbalism quests |
| Caelindra | Stone Hearth | Bard, sings world events at noon |
| Marta | The Rusty Pick (Lore-only) | Innkeeper (Lore-only) |
| Old Pell | Pell's Depot (Lore-only) | Merchant (Lore-only) |
| Rook | Grimstone (Lore-only) | Town guard / watcher (Lore-only) |
| Valdric | Grimstone (Lore-only) | Mercenary, quest giver (Lore-only) |
| Senna | Grimstone (Lore-only) | Local resident (Lore-only) |

NPC dialogue is LLM-generated using `build_npc_prompt()` with context: season, time of day, CHA modifier, active quest status, and NPC-specific topics.

---

## Quests

| Quest | NPC | Level | Tasks | Rewards |
|:--|:--|:--|:--|:--|
| A Stranger in the Mud | Elara | 1 | Talk barkeep, hemlock, elara | 50 XP, 20 Gil |
| The Darkening Woods | Guard | 3 | Hunt whisperwood_deep, talk guard | 150 XP, 100 Gil, lucky_charm |
| Sister Maren's Request | Maren | 4 | Kill bandit, talk maren | 200 XP, 50 Gil, potion recipe, silverleaf |
| The Aeridorian Signal | Elara | 5 | Complete dungeon, talk elara | 500 XP, 200 Gil, lightstone |
| What Sleeps Beneath | Guard | 7 | Kill frost_wolf, kill_owlbear, talk guard | 1200 XP, 350 Gil, ironbark_tonic |
| The Merchant's Gambit | Traveling merchant | 8 | Kill bandit, talk merchant | 800 XP, 300 Gil, potion_standard |
| Shadows Over Grimstone | Watchtower guard | 9 | Complete dungeon, talk guard | 1000 XP, 400 Gil, ironbark_tonic |
| The Tithe Collector | Elara | 10 | Kill tithe collector, talk Elara | 1400 XP, 600 Gil, void_band |
| The Final Silence | Elara | 9 | Pray at shrine, complete dungeon, talk elara | 1500 XP, 500 Gil, amulet_health |
| The Waking Metal | Elara | 11 | Kill iron_golem, talk elara | 2500 XP, 800 Gil, void_band |
| The Darkening | Guard | 13 | Kill shadow_lich, talk guard | 3500 XP, 1500 Gil, mox_pearl |
| The Last Guardian | Elara | 15 | Complete dungeon, talk elara | 5000 XP, 5000 Gil, the_end |
| What Sings Below | Hooded figure (Stone Hearth) | 15 | Look at the Aeridor crystals, kill the Crystal Dragon (Ironvein Deep floor 33), talk hooded figure | 6000 XP, 2000 Gil, aeridor_shard |

*Note: This is the complete list of 13 quests in the database (`quest_registry.QUESTS`). The two Grimstone quests were given by Pell and Valdric, who are not NPCs anyone can talk to; since 26 Sept they are offered by the traveling merchant and the Watchtower guard, and a test holds every quest to a real NPC.*

---

## Calendar, Seasons & Day/Night Shifts

The in-game calendar tracks seasons and special days with gameplay effects:

| Season | Months |
|:--|:--|
| Spring | Months 1-3 |
| Summer | Months 4-6 |
| Autumn | Months 7-9 |
| Winter | Months 10-12 |

Special days carry unique buffs (see `calendar.py` for full list): XP bonuses, hunt bonuses, attack bonuses, shrine effects, shop discounts, etc.

### Day/Night Mechanics
Overworld activities change dynamically based on time of day (Day is 6 AM to 6 PM, Night is 6 PM to 6 AM):
- **Night-time combat modifiers**: Undead encounter spawn rates are doubled.
- **Tier shift**: 25% chance during night hunts to shift the encounter target up by one tier (e.g. Easy becomes Medium, Hard becomes Deadly), providing higher challenge and better loot.
- **Morning healing**: Sylvan sprites may restore minor health passively to players exploring in the morning.

---

## Noon Events

At 12:00 PM (Noon) daily, a random dynamic world event is selected from the active event pool and triggered in `#aethelgard` (with temporal effects persisting until the next noon event).

### Active Noon Event Pool (33 total)

| Event | Code Key | Type / Impact | Description |
|:--|:--|:--|:--|
| 🔔 Village Alarm | `raid` / `invasion` | Combat (Defense) | Scaled raid on Oakhaven by waves of random themed monsters. Players in town and active in the last 48 hours defend to earn XP/Gil. |
| 👁️ A Veiled Elder Appears | `oracle` | Buff | Grants a random class check buff (STR +1, DEX +1/2, INT +2, WIS +2, etc.) to present players. |
| 📬 Moogle Mail Drop | `moogle` / `mail` | Items | Moogles drop random items (Healing Herb, Bandage, Tonic, Aeridor Shard, Lucky Charm) to present players. |
| 💎 Aeridorian Tremor | `tremor` / `aeridor` | XP | Ruin resonance tremor grants all present players +50 XP. |
| 🔪 Tonberry Procession | `tonberry` / `procession` | Mixed | Tonberries march through town. 80% chance for +10-25 XP and +10-30 Gil; 20% chance to lose 5-12 HP from eye contact. |
| ⛈️ Storm of the Spine | `storm` | Buff + XP | Spine storm hits town, granting class-specific buffs and +5-14 XP to present players. |
| 🐪 Caravan Arrival | `caravan` | Shop | Spawns the Corvus Road Trading Co. caravan (Trade Road) selling Tier 3 gear (limit 1 purchase/customer). |
| 🎵 Bard Performance | `bard` | Narrative | Caelindra the bard performs an LLM ballad summarizing recent world events and top adventurers. |
| 🤖 Watchtower Intrusion | — | Combat (Defense) | Ranks of Aeridorian constructs attack. Defender waves fight constructs for XP and Gil. |
| 🥀 Whisperwood Blight | — | Penalty | Mist creeping from the forest edge ruins a crop plot for up to 3 random farm owners in Oakhaven. |
| 🕯️ Procession of Pilgrims | — | Buff + Healing | Pilgrims arrive, restoring +10 HP, granting Blessed to present players, and enhancing shrine blessings until the next noon event. |
| 👁️ Night Terror Warning | — | Mechanics Mod | Shadow beast warning shifts all solo hunts up by 1 threat tier (+1 difficulty, better loot/XP) until the next noon event. |
| 🤖 Construct Breach | `construct` | Combat (Defense) | An intense breach of constructs attacking Oakhaven town gates. |
| 🐪 Caravan Ambush | `ambush` | Combat (Defense) | A raid defense centered on protecting the merchant caravan cargo from bandits on the Trade Road. |
| 📋 Market Glut / Shortage | `market` | Economy Mod | 50% chance for Market Glut (all shop prices -20% until the next noon event) or 50% chance for Bandit Blockade (prices +25% until the next noon event). |
| 🌸 Whisperwood Bloom | `bloom` | Spawn Mod | Pollen bloom increases all Whisperwood edge/deep forest event chances by +15% until the next noon event. |
| 🕯️ Shrine Vigil | `vigil` | Buff Window | Enhanced blessing window at Oakhaven Shrine (grants +5 HP and Blessed) until the next noon event. |
| 📋 Missing Person Notice | `missing` | World Quest | Distress notice posted for a random villager. Players must hunt/scout in a target zone to find and escort them back; the rescue is announced in `#aethelgard`. |
| ⚙️ Ironclad Guild Envoys | `ironclad_envoys` | Economy Mod | Guild envoys buy up local supplies, inflating Hemlock's and Caravan prices by 15% until the next noon event. |
| 🌊 The Silverstream Runs Black | `silverstream_blackwater` | Environment | Murky runoff taints Tricklebrook Pond headwaters; fishing is temporarily disabled/dangerous until the next noon event. |
| 🌘 The Hooded Figure's Vigil | `hooded_figures_vigil` | Buff | Stranger at the hearth casts an eerie shadow; patrons present at Stone Hearth receive the Veiled Watched buff. |
| 📜 Caelindra's Lost Verse | `caelindras_lost_verse` | XP / Lore | Caelindra recites an ancient Aeridorian verse, granting Stone Hearth patrons +15 XP. |
| 🔭 The Watchtower's Silence | `watchtower_silence` | Scout Mod | On-edge guards share detailed logs; scouts visiting the Watchtower get enhanced scouting reports until the next noon event. |
| 🧪 Silvani Antidote Run | `silvani_antidote_run` | Items | A Silvani hunter slips into town and leaves a free bandage for each present adventurer. |
| 🕳️ Bank Alarm — Vault Breach | `iron_magpies_heist` | Combat / Penalty | Bank alarm sounds as an Iron Magpies master thief (Darek Shadow-Bound, Garrett the Vault-Creeper, or Felix "Ghost-Hand" Pryce) breaches the vault. Town defenders pool damage against the boss. Repelling the operative secures the vaults and awards XP/Gil; failing or ignoring the heist takes 5% of the bank balance of every character active in the last 48 hours, as an uncapped Gil sink. |
| 🍃 Whisperwood Boundary Shift | `boundary_shift` | Mechanics Mod | Border stakes shifted; Whisperwood Edge solo hunts shift up by 1 tier (increased difficulty/loot) until the next noon event. |
| 🫙 The Sealed Wax Jar | `sealed_wax_jar` | Shop Special | Hemlock opens a wax jar, offering Lucky Charms at a special discount (20 Gil) until the next noon event. |
| 🌙 Elara's Private Ritual | `elaras_private_ritual` | XP / Lore | Oakhaven residents witness Elara performing a shrine ritual, granting +10 XP. |
| 🌠 Starfall | `starfall` | Rare Mod | Fallen Star events by day as well as night, at three times their weight, until the next noon event. |
| 📚 The Wandering Archivist | `scholar` / `archivist` | Lore Mod | Archivist Venn arrives; the four lore events are twice as likely until the next noon event. |
| 🪙 The Gilded Migration | `migration` / `gilded` | Rare Mod | Rare variants 1 in 10 instead of 1 in 40 until the next noon event. |
| 🕯️ The Ghost Caravan | `ghost_caravan` | Spawn Mod | More undead, and forest events +10% everywhere, until the next noon event. |
| 🌑 The Hollow Sun | `eclipse` / `hollow_sun` | Mechanics Mod | Half the weight of the others. Monsters a tier stronger, more undead, rare variants 1 in 10, until the next noon event. |

---

## Balance targets

The budgets gear and monsters are held to. Change them deliberately: the DEF soft-cap and global cap in CLAUDE.md §4 depend on them.

### Equipment stat budgets

| Tier | Weapon ATK | Weapon DMG | Die | Proc | Drop Source |
|---|---|---|---|---|---|
| T1 | +0 | +0 | d6 | — | Shop + loot |
| T2 | +1 | +0 | d8 | — | Shop + loot |
| T3 | +1 | +1 | d8/d10 | 1d4 | Loot only |
| T4 | +2 | +1 | d10 | 1d6 | Loot only |
| T5 | +2 | +2 | d10/d12 | 1d8 | Boss loot |
| T6 | +3 | +2 | d12 | 1d10 | Boss loot (deadly/boss) |
| T7 | +3 | +3 | d12 | 1d12 | Boss loot only |

Defensive gear DEF ranges: Armor max 8, Headgear max 3, Boots max 3, Accessories max 2. Armor stat bonuses capped at +1. The gear soft-cap (`min(10, raw) + max(0, raw-10)//2`) correctly prevents DEF stacking from becoming degenerate.

### Power curve

Measured, not estimated: `tools/simulation/progression_sim.py --policy hunt --lives 5 --days 150`
(25 characters, five classes, six hunts a day, the real combat engine and loot tables, potions
bought and drunk, a retreat when a fight goes badly). Re-run it after any change to combat,
monsters, loot, the XP table or prices, and compare by level; `--policy dungeon` spends hunts
on dungeons and the Spine.

| Levels | Days a level | Rounds a fight | HP lost a fight | Deaths / 100 fights | Retreats / 100 | Gil a day |
|:--|:--|:--|:--|:--|:--|:--|
| 1–3 | ~2 | 4–5.5 | 16–25% | 0.3–2.8 | 4–11 | 90–150 |
| 4–6 | 2–4.5 | 6–7 | 19–29% | 0.3–1.2 | 5–19 | 230–340 |
| 7–9 | 9–13 | 7.7–8.9 | 26–30% | 0.4–2.6 | 7–28 | 340–810 |
| 10–12 | 11–16 | 9.4–9.9 | 31–36% | 0.4–0.8 | 10–16 | 900–1,450 |
| 13–15 | 11–12 | 7–8.4 | 21–28% | 0–0.5 | 1–7 | 2,400–3,400 |

A daily hunter reaches level 15 in a median of about 80–95 days. Before the November 2026 pass the
same run never got there: four in ten level-1 fights ended in a blackout, and levels 4 and 7 (the
deep woods, the ruins) each held a character for 50–70 days. At the cap income was ~9,000 gil a day,
three quarters of it from selling drops.

**Where gil goes.** Potions and the inn (both scale with level), Hemlock's Tier 2 gear (~250–300g a
piece) from level 3, housing (1,000 / 5,000 / 15,000 / 40,000), pets and furniture, then Hemlock's
rework at the cap (up to 150,000g per top piece).

## Progression

| Level | XP Required | Level | XP Required |
|:--|:--|:--|:--|
| 2 | 200 | 9 | 16,000 |
| 3 | 500 | 10 | 25,000 |
| 4 | 900 | 11 | 38,000 |
| 5 | 1,400 | 12 | 57,000 |
| 6 | 2,500 | 13 | 92,000 |
| 7 | 4,500 | 14 | 136,000 |
| 8 | 8,500 | 15 | 193,000 (cap) |

Every step costs more than the one before it; the table is set from measured XP a day at each level.

**HP gain per level** = `HP_per_level[class] + CON modifier` (minimum 1).

**Stat choices** at levels 4, 8 and 12 are queued, one per milestone (`progression.queue_stat_choice`), so a single XP award that crosses several milestones keeps every choice. Raising CON adds HP retroactively by the *modifier* change times level (`retroactive_hp_gain_for_con_change`), not per point.

**Advancement** unlocks at level 5. A character loaded at level 5+ with no `advanced_class` is re-armed for the choice (`character_manager._migrate_advancement_pending`); choosing "stay" sets `advanced_class` to the base class, so it is offered once.

Daily hunts reset at midnight. Dawn announcements post to `#aethelgard`.

---

## UI System

The game uses **Discord button-based navigation** (no command syntax shown to players). Key UI views:

- **HUD** — Main status embed with HP bar, XP, Gil, equipment, hunts
- **Navigation View** — Travel buttons for connected locations
- **Shop View** — Buy/sell item selects, including a **Consumable Quantity Picker** for bulk transactions
- **Dungeon View** — Direction buttons (N/S/E/W), Use Item, Leave
- **Combat View** — Attack, Flee, Use Item buttons
- **Class Advancement View** — Choice buttons at level 5

HUD title format: `(Title) Class Lv.N` — e.g. `(Channeler) Mage Lv.3`

### Background Tasks & Automation
- **Dawn Reset (Midnight):** Resets daily hunts, clears temporary conditions, triggers farm growth, and logs dawn announcements.
- **Noon Events (Noon):** Triggers dynamic world events like Caravan Arrivals or Caelindra's Bard Performances.
- **Automatic XP:** Non-combat actions (`!rpg action`) and combat wins automatically grant and distribute XP to the player/session.

---

## Narration System

Kaia (the bot's persona) narrates via LLM. Ground-truth blocks are injected into prompts so Kaia never decides outcomes — she only narrates what Python already resolved.

**Hunt reports are posted once per player per day** (`utils/ttrpg/outing.py`). Fights and forest events are recorded per player, and an outing's results are merged into a daily accumulator when it ends. At midnight, before hunts reset, Kaia combines all of that player's outings (including a still-open outing) into one narrated report for `#aethelgard`. Failed generation or delivery stays in `memory/ttrpg/outings/untold/` for retry. Moving between hunting grounds remains one outing; returning to town no longer creates a separate post.

Each open outing, daily accumulator, and untold report is bound to the player ID encoded in its filename. A mismatched embedded `uid` is preserved and fails closed before cross-player merging, finalization, or posting. Legacy outing records without a `uid` adopt the filename owner.

The daily digest is posted to **#aethelgard** (`discord.rpg_channel`) so players can follow what everyone did that day; its totals combine the day's fights, XP, Gil, loot, events, and other outing notes. The final report is first persisted in `memory/ttrpg/outings/untold/`; if generation or delivery fails, or the bot restarts mid-report, that same daily digest is retried at boot. The prompt retains creature descriptions, how fights felt (close calls, clean wins, lucky strikes), the latest HP, sensory detail, and Kaia's lowercase GM voice.

Prompt builders in `rpg_prompt_builder.py`:
- `build_look_prompt()` — description of a location on `!rpg look`
- `build_rumor_prompt()` — a tavern rumor
- `build_npc_prompt()` — NPC dialogue (with CHA context)
- `build_event_prompt()` — Admin-triggered world events
- `build_outing_summary_prompt()` — one paragraph for a whole trip out (fights are not narrated one by one; see CLAUDE.md §4)

All LLM calls are GPU-guarded via `gpu_memory_manager.run_with_gpu_guard()` and wrapped in try/except — narration is always best-effort, game state is never dependent on LLM success.

---

*Aethelgard is a persistent world running inside Kaiacord.*
*Kaia narrates. Python decides. The world doesn't wait for you.*