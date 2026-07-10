# ⚔️ Aethelgard — System Reference & Player Manual
*Build 0.4.0 · April 25, 2026 — Endgame Expansion & Balance*

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
├── forest_events.py               ← 21 forest event handlers (Sylvan Sprites, Tonberry, etc.)
├── look_targets.py                ← Hardcoded "look at <thing>" flavor text per location
├── loot_tables.py                 ← Tier-aware loot drops from monsters and dungeon chests
├── micro_events.py                ← Overworld traveling events, weather discoveries, and streak rewards
├── monster_registry.py            ← Full bestiary: 365 monsters across 7 tiers
├── npc_registry.py                ← NPC definitions: Elara, Hemlock, Mira, Guard, Maren, Bard
├── progression.py                 ← XP thresholds, level-up, daily hunt reset, condition expiry
├── quest_registry.py              ← Quest definitions and lookup helpers
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

1. **Player sends `!rpg <command>`** → `rpg_handler.py` routes to handler function
2. **Handler loads sheet** via `character_manager.load(uid)` → JSON from `memory/ttrpg/characters/`
3. **Game logic** runs deterministically (dice_engine, combat_engine, shop, etc.)
4. **Kaia narrates** via `rpg_prompt_builder.py` → GPU-guarded LLM call → flavor text embed
5. **Sheet saved** back to disk → UI view (discord buttons) returned to player

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

Stats rolled with 4d6 drop lowest, six times. Type `!rpg` to open the HUD.

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
                  [Spine of the World]
                         |
                   [Grimstone]
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
| **Oakhaven** | Look, map, calendar, weather, notices, quests, deliver |
| **Stone Hearth** | Rest (5g), drink (+3 temp HP, 2g), gamble (10g), rumor, talk NPCs |
| **Hemlock's Store** | Shop, buy, sell, inventory, talk |
| **Shrine** | Pray (Blessed), offer Gil→XP, fountain (full heal 1/day), look flame/altar |
| **Watchtower** | Scout (1/day), talk guard |
| **Maren's Hut** | Brew alchemy recipes, talk Maren |
| **Bank** | Deposit, withdraw (protects Gil from blackout loss) |
| **Housing District** | Buy a home, `!rpg home` (Farming, Pets, Decorate) |
| **Tricklebrook Pond** | `!rpg fish`, `!rpg fish_shop` (Buy bait/poles) |
| **Grimstone** | Look, travel to Spine, talk to NPCs |
| **The Rusty Pick** | Rest (7g), drink (+4 temp HP, 3g), rumor |
| **Pell's Depot** | Shop, buy, sell, talk Pell |
| **Caravan** | Only present during certain noon events. |
| **Hunting zones** | Hunt (1 of 5 daily hunts), look |

---

## Combat

Fully automatic. Player never touches dice.

**Attack:** `d20 + class_attack_mod + weapon_bonus vs monster_DEF`
**Damage:** `weapon_die + class_attack_mod`
**Player DEF:** `10 + DEX_mod + effective_gear_def` (Max `Level * 1.5 + 12`). Gear DEF is soft-capped: `min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2`.
**Monster ATK:** Uses actual monster ATK stat. Overworld scaling uses logarithmic dampening (max 1.35x based on distance).
**Crit (nat 20):** Damage dice doubled
**Fumble (nat 1):** Auto-miss

### Weapon Procs
Select T3+ weapons possess inherent elemental procs. These trigger independently on standard hits (10% chance) and critical hits (50% chance). They scale in extra damage from 1d4 to 1d12 based on weapon tier, and can trigger simultaneously alongside Class Procs.

### Inventory Capacity Cap
Players are subject to a strict inventory size limit of **50 items**. Any purchase, brew, or loot drop that would cause the inventory to exceed 50 is blocked (items dropped in combat are left behind on the ground with an `🎒 [Inventory Full]` message).

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

Each hunt costs 1 of 5 daily hunts. Hunts may trigger a **forest event** instead of a monster. **Events are free — they do not consume a daily hunt.** The player still gets their full 5 hunts for combat XP.

| Location | Event Chance | Rec. Level |
|:--|:--|:--|
| Whisperwood Edge | 20% | 1+ |
| Trade Road | 18% | 2+ |
| Whisperwood Deep | 15% | 4+ |
| Aeridor Ruins | 10% | 7+ |

### Forest Events (21 total)

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
A massive 77-floor mega-dungeon located past Grimstone. Unlike procedural dungeons, the Spine features a fixed, hand-crafted 24x24 layout with intricate floor connectivity, static encounters, dynamic hallway traps, and unique bosses. It features checkpoint lifts every 5 floors and progressive floor-based monster scaling (e.g. `mob_hp_cap = 80 + floor_num * 3` and `mob_atk_cap = 12 + floor_num // 5`).

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
Some shrine rooms contain a **sealed Aeridorian shrine** with a three-flame seal. Players who've studied the flame and altar at the Oakhaven Shrine (`look flame`, `look altar`) can interact.

### Boss Scaling & Encounters
Boss stats scale to player level: `0.45x at L1 → 1.0x at L15`. Dungeon Boss ATK caps are tightly calibrated to ensure a ~50-55% hit rate.
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
| Smoke Bomb | Blood Thistle + Topaz | `smoke_bomb` (Flee combat with 0 XP loss) |
| Warding Salve | Dire Root + Opal | `warding_salve` (Reduce next hit dmg by 5) |
| Frenzy Draught | Blood Thistle + Jacinth | `frenzy_draught` (+1 attack, -2 DEF) |
| Moonwater | Silverleaf + Black Pearl | `moonwater` (Full HP restore) |
| Trap Kit | Dire Root + Fire Opal + Topaz | `trap_kit` (2d8 damage trap) |

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
| Trap Kit | — | 60g | 3 |

### Buff Potions & Utility (Crafted)
| Item | Effect |
|:--|:--|
| Experience Tonic | +25% XP on your next hunt / dungeon kill |
| Hunter's Draught | Instantly refunds 1 daily hunt upon use |
| Ironbark Tonic | Grants `Fortified` (+2 DEF for one entire combat encounter) |
| Firebrew | Grants `Embered` (+2 ATK for one entire combat encounter) |
| Smoke Bomb | Instantly escape combat safely without XP/Gil loss |
| Warding Salve | Grants `Warded` (reduces next damage hit by 5) |
| Frenzy Draught | Grants `Frenzied` (+1 extra attack, -2 DEF for one entire combat encounter) |
| Trap Kit | Lay down a trap in a dungeon room, dealing 2d8 physical damage to next monster |

---

## Housing System

Players can purchase a home in the **Housing District** (`!rpg go housing_district`) for an initial 50k Gil (Hut). Upgrading unlocks more options. Access your home menu using `!rpg home`.

### Farming
Grow crops in your farming plots. Seeds are bought from Hemlock or found. Crops grow over time/interactions, yielding items and cooking ingredients.

### Pets
Adopt pets to live in your home from Pip the Pet Vendor in the Housing District. Pets require daily feeding (paid in gold based on food type) and provide powerful passive bonuses when well-fed:
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
| Fortified | Ironbark Tonic | +2 DEF applied for one entire combat encounter |
| Embered | Firebrew | +2 ATK applied for one entire combat encounter |
| Warded | Warding Salve | Reduces next incoming damage hit by 5 |
| Frenzied | Frenzy Draught | +1 extra attack, but -2 DEF for one entire combat encounter |
| Sharp Mind | Old Man's Riddle | +2 to next INT check |
| Battle Focus | Veiled Elder (Warrior) | +1 to STR checks |
| Forest Sight | Veiled Elder (Ranger) | +1 to DEX checks |
| Resonance Link | Veiled Elder (Mage) | +2 to INT checks |
| Shadow Step | Veiled Elder (Rogue) | +2 to DEX checks |
| Divine Clarity | Veiled Elder (Cleric) | +2 to WIS checks |
| Tree Memory | Whisper in Bark | -2 damage from natural sources |
| Wisp Ward | Twin Wisps (ignored both) | Light protective ward |
| Aeridorian Attunement | Strange Statue | +1 ATK in ruins |

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
| Marta | The Rusty Pick (Grimstone) | Innkeeper |
| Old Pell | Pell's Depot (Grimstone) | Merchant, hardware supplies |
| Rook | Grimstone | Town guard / watcher |
| Valdric | Grimstone | Mercenary, quest giver |
| Senna | Grimstone | Local resident |

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
| The Merchant's Gambit | Pell | 8 | Kill bandit, talk Pell | 800 XP, 300 Gil, potion_standard |
| Shadows Over Grimstone | Valdric | 9 | Complete dungeon, talk Valdric | 1000 XP, 400 Gil, ironbark_tonic |
| The Tithe Collector | Elara | 10 | Kill tithe collector, talk Elara | 1400 XP, 600 Gil, void_band |
| The Final Silence | Elara | 9 | Pray at shrine, complete dungeon, talk elara | 1500 XP, 500 Gil, amulet_health |
| The Waking Metal | Elara | 11 | Kill iron_golem, talk elara | 2500 XP, 800 Gil, void_band |
| The Darkening | Guard | 13 | Kill shadow_lich, talk guard | 3500 XP, 1500 Gil, mox_pearl |
| The Last Guardian | Elara | 15 | Complete dungeon, talk elara | 5000 XP, 5000 Gil, the_end |

*Note: This is the complete list of 12 quests currently active in the system, spanning levels 1 through 15.*

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

## Progression

| Level | XP Required | Level | XP Required |
|:--|:--|:--|:--|
| 2 | 300 | 9 | 48,000 |
| 3 | 900 | 10 | 64,000 |
| 4 | 2,700 | 11 | 85,000 |
| 5 | 5,000 | 12 | 112,000 |
| 6 | 11,000 | 13 | 148,000 |
| 7 | 19,000 | 14 | 195,000 |
| 8 | 28,000 | 15 | 256,000 (cap) |

**HP gain per level** = `HP_per_level[class] + CON modifier` (minimum 1).

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

Kaia (the bot's persona) narrates all game events via LLM. Ground-truth blocks are injected into prompts so Kaia never decides outcomes — she only narrates what Python already resolved.

Prompt builders in `rpg_prompt_builder.py`:
- `build_combat_prompt()` — Hunt/dungeon combat narration
- `build_action_prompt()` — Skill check narration
- `build_npc_prompt()` — NPC dialogue (with CHA context)
- `build_event_prompt()` — Admin-triggered world events
- `build_event_narration_prompt()` — Forest event narration
- `build_levelup_prompt()` — Level-up flavor text

All LLM calls are GPU-guarded via `gpu_memory_manager.run_with_gpu_guard()` and wrapped in try/except — narration is always best-effort, game state is never dependent on LLM success.

---

*Aethelgard is a persistent world running inside Kaiacord.*
*Kaia narrates. Python decides. The world doesn't wait for you.*