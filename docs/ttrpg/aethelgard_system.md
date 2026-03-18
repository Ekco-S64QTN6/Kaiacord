# ⚔️ Aethelgard — Official Player Manual
*Build 0.1.0 · March 17, 2026*

> *"Oakhaven was built on the bones of Aeridor. Everything here is built on something older."*

---

## The World

Aethelgard is a persistent world. It runs at all times. No one starts it or stops it. You drop in whenever you want and pick up where you left off.

The world is low magic, high potential. True spellcasting is rare and often dangerous. The Whisperwood presses against the eastern edge of Oakhaven and has no interest in your plans. The ruins of Aeridor — the civilization that once mastered the earth itself — lie two days east and hum with something that predates memory.

You start in **Oakhaven**, a muddy settlement of around two hundred souls on the edge of the forest. You will probably die here several times. That is normal.

---

## Where to Play

The game runs in two places on the server:

- **`#aethelgard`** — Broadcast channel. Dawn announcements and world events appear here. You cannot play here directly.
- **`#aethelgard-tales`** — Forum channel. Create your own thread here to play. Your thread is your chronicle. Multiple players can run simultaneously in separate threads without interference.

All characters share one world. Your Gil, XP, equipment, and location are yours across every session.

---

## Getting Started

Create your character once. It is permanent.

```
!rpg new <Name> <Race> <Class>
```

**Example:** `!rpg new Vex Elf Ranger`

Stats are rolled automatically using 4d6 drop lowest, six times.

After creation, type `!rpg` to open your HUD and begin.

---

## Races

| Race | Bonuses |
|:--|:--|
| **Human** | +1 to all stats |
| **Elf** | DEX +2, INT +1, WIS +1 |
| **Silvani** | DEX +2, WIS +2 |
| **Dwarf** | CON +2, STR +1 |
| **Glimmerkin** | CHA +2, INT +1, DEX +1 |
| **Veiled** | INT +2, CHA +2 |

The Silvani are a reclusive race deeply connected to the Whisperwood. The Veiled are pale, silver-haired, and regarded with suspicion by most of Oakhaven.

---

## Classes

| Class | Attack Stat | HP Die | Flavor |
|:--|:--|:--|:--|
| 🗡️ **Warrior** | STR | d10 | Heaviest hits, highest HP |
| 🏹 **Ranger** | DEX | d8 | Consistent damage, forest-attuned |
| 🔮 **Mage** | INT | d4 | Glass cannon. INT drives everything. |
| 🗝️ **Rogue** | DEX | d6 | Crits on 19-20, not just 20 |
| ✨ **Cleric** | WIS | d8 | Healing bonus on consumables |

**Level 1 HP** = HP die + CON modifier + 1 (minimum 1).

The attack stat is used for both to-hit rolls and damage. A Mage with INT 18 hits harder than a Mage with STR 12, regardless of weapon.

---

## The HUD

Type `!rpg` at any time to see your status board.

```
⚔️  VEX  |  Ranger Lv.3  |  Edge of the Whisperwood
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❤️  HP:  18/24  ████████████░░
✨  XP:  450/900  ██████░░░░░░░░  → Lv.4
💰  Gil: 35g

⚔️  Weapon: Shortbow (+4 ATK, d6)
🛡️  Armor:  Leather Armor (+2 DEF)

🎯  Hunts remaining: 4/5

Nearby: Oakhaven Town Square · Whisperwood Deep (hunting)
```

The HP bar color updates dynamically:
- 🟩 **Green** — Above 60% health
- 🟨 **Yellow** — 30–60% health
- 🟥 **Red** — Below 30% health
- 💀 **Gray** — Defeated

---

## The World Map

```
                    [Spine of the World]
                           |
                     [Grimstone]  ← 3 days north
                           |
               [Trade Road] ──── [Aeridor Ruins]  ← 2 days east
                           |
                     [OAKHAVEN]  ← hub
                    /    |    \
           [Stone  ] [Hemlock's] [Shrine of
            Hearth]  [Store]      Silent Ones]
                           |
                   [Whisperwood Edge]  ← lvl 1+
                           |
               [Whisperwood Deep]  ← lvl 4+
                           |
                   [Aeridor Ruins]  ← lvl 7+
```

---

## Locations

### 🏘️ Oakhaven Town Square
The hub. Muddy, watchful, functional. All roads lead here.

**Commands here:** `!rpg look` · `!rpg map` · `!rpg talk elara` · `!rpg calendar` · `!rpg notices`

---

### 🍺 The Stone Hearth Inn
OakHaven's only inn. Low beams. A fire that's always lit. Mira keeps the peace.

| Command | Effect | Cost |
|:--|:--|:--|
| `!rpg rest` | Restore full HP | 5 Gil |
| `!rpg drink` | +3 temporary HP (until next rest) | 2 Gil |
| `!rpg gamble` | d6 vs d6 — win doubles your stake | 10 Gil |
| `!rpg rumor` | Kaia generates Aethelgard gossip | Free |
| `!rpg talk barkeep` | Speak with Mira | Free |

The ale warmth bonus (+3 HP) is removed when you rest. You cannot stack it.

---

### 🛒 Hemlock's General Store
Cluttered shelves. The smell of dried herbs and iron. Hemlock knows where everything is, somehow.

| Command | Effect |
|:--|:--|
| `!rpg shop` | View full inventory and prices |
| `!rpg buy <item>` | Purchase an item (auto-equips if slot empty) |
| `!rpg sell <item>` | Sell at 50% value |
| `!rpg talk hemlock` | Speak with Old Man Hemlock |

**Hemlock stocks tier 1–2 only.** High-tier equipment comes from the ruins or Grimstone. Prices are adjusted by your **Reputation**.

---

### ⛩️ Shrine of the Silent Ones
Crumbling stone. Ancient carvings worn smooth. Someone left fresh flowers this morning. If you blackout in the field, you wake here.

| Command | Effect | Cost |
|:--|:--|:--|
| `!rpg pray` | Blessed condition: +2 to all rolls on next hunt (once/day) | Free |
| `!rpg offer <amount>` | Donate Gil for XP (1 XP per Gil, 20 XP/day cap) | Gil |

---

### 🏹 The Watchtower
Rickety stairs. A view of the Whisperwood canopy. Two bored guards who know more than they let on.

| Command | Effect |
|:--|:--|
| `!rpg scout` | Preview monster tier distribution at all hunting grounds (once/day) |
| `!rpg talk guard` | Speak with the Watchtower guards |
| `!rpg notices` | Read the square's board for events and duels |

---

### 🧪 Sister Maren's Hut
A small lean-to tucked behind the shrine. The air is thick with the scent of drying herbs.

| Command | Effect |
|:--|:--|
| `!rpg brew` | Combine ingredients into alchemy recipes |
| `!rpg talk maren` | Speak with Sister Maren |

---

### 🏦 Oakhaven Bank
A sturdy stone building near the square. Secure and formal.

| Command | Effect |
|:--|:--|
| `!rpg bank balance` | Check your stored Gil |
| `!rpg bank deposit <amt>` | Store Gil safely (protect from blackout loss) |
| `!rpg bank withdraw <amt>` | Retrieve your Gil |

---

## Hunting

Hunt from any location marked *(hunting)* on your HUD. Each hunt costs 1 of your 5 daily hunts.

```
!rpg hunt
```

Python selects a weighted random monster appropriate for your location, resolves the full combat exchange, applies all damage and XP automatically, and Kaia narrates the outcome. You never touch the dice.

After a hunt, if the monster survives, use `!rpg attack` to continue the fight or `!rpg flee` to attempt escape.

### PvP Duels (Non-Lethal)
Challenge another player to a duel. Duels always stop at 1 HP ("Yield!").

```
!rpg duel <@user>
!rpg accept
```
Wins and losses are recorded on the **Notice Board**.

**Daily hunts reset at midnight server time.** A dawn announcement posts in `#aethelgard` when this happens.

### Hunting Locations

| Location | Rec. Level | Monsters |
|:--|:--|:--|
| Edge of the Whisperwood 🌲 | 1+ | Trivial–Easy |
| The Trade Road 🛤️ | 2+ | Easy |
| Whisperwood Deep 🌑 | 4+ | Easy–Hard |
| Aeridor Ruins 🏚️ | 7+ | Medium–Deadly |

You can enter any area regardless of recommended level. You will be warned. The monsters will not care.

---

## Combat

Combat is fully automatic. You never calculate anything.

**Player attack formula:**
```
d20 + class_attack_modifier + weapon_attack_bonus  vs  monster DEF
```

**Player defense formula:**
```
10 + DEX modifier + armor_defense_bonus
```

**Damage on hit:**
```
weapon_damage_die + class_attack_modifier
```

**Critical hit (natural 20):** Damage dice doubled.
**Fumble (natural 1):** Automatic miss, no damage.

### Combat Streak 🔥
Consecutive victories grant a momentum bonus:
- **Streak 2+:** +1 to-hit and a Gil multiplier on drops.
- **Reset:** Streak ends on Flee or Blackout.

### Status Effects

| Condition | Effect |
|:--|:--|
| ✨ **Blessed** | +2 to all attack and stat rolls. Consumed after first combat. |
| 🍺 **Ale Warmth** | +3 temporary HP. Cleared on rest. |
| 🧠 **Sharp Mind** | +2 to next INT check. From Old Man's Riddle event. |
| 🌿 **Resonance Link** | +2 to INT checks. Granted by Veiled Elder (Mage). |
| 🌑 **Shadow Step** | +2 to DEX checks. Granted by Veiled Elder (Rogue). |
| ☀️ **Divine Clarity** | +2 to WIS checks. Granted by Veiled Elder (Cleric). |
| 🗡️ **Battle Focus** | +1 to STR checks. Granted by Veiled Elder (Warrior). |
| 🌲 **Forest Sight** | +1 to DEX checks. Granted by Veiled Elder (Ranger). |

---

## Blackout

If your HP reaches 0, you have blacked out.

- Lose **10% of current XP**
- Lose **5% of current Gil**
- Wake at the **Shrine of the Silent Ones** with **1 HP**
- Kaia narrates the recovery

Use `!rpg rest` at the Stone Hearth to recover before hunting again.

---

## Progression

### XP Thresholds

| Level | XP Required |
|:--|:--|
| 2 | 300 |
| 3 | 900 |
| 4 | 2,700 |
| 5 | 6,500 |
| 6 | 14,000 |
| 7 | 23,000 |
| 8 | 34,000 |
| 9 | 48,000 |
| 10 | 64,000 |

**Level-up HP gain** = HP_per_level[class] + CON modifier (minimum 1 per level).

XP is awarded automatically on monster kills and forest events. You never type `!rpg xp` yourself — that's an admin command for story milestones.

---

## Equipment

### Weapons available at Hemlock's

| Item Key | Name | ATK Bonus | Damage | Price |
|:--|:--|:--|:--|:--|
| `rusty_dagger` | Rusty Dagger | +0 | d4 | 5g |
| `wooden_club` | Wooden Club | +0 | d4 | 3g |
| `hand_axe` | Hand Axe | +1 | d6 | 18g |
| `shortbow` | Shortbow | +1 | d6 | 20g |
| `iron_sword` | Iron Sword | +2 | d6 | 35g |
| `wooden_staff` | Wooden Staff | +1 | d6 | 8g |
| `spear` | Spear | +2 | d8 | 40g |
| `crossbow` | Crossbow | +3 | d8 | 55g |
| `battle_axe` | Battle Axe | +3 | d8 | 60g |
| `iron_staff` | Iron-Shod Staff | +2 | d8 | 30g |

*Staves are typically carried by Mages and Clerics. Hemlock will sell to anyone.*

### Armor available at Hemlock's

| Item Key | Name | DEF Bonus | Price |
|:--|:--|:--|:--|
| `travelers_cloak` | Traveler's Cloak | +0 | 5g |
| `mages_robe` | Mage's Robe | +1 | 12g |
| `leather_armor` | Leather Armor | +2 | 20g |
| `studded_leather` | Studded Leather | +3 | 40g |
| `silken_robe` | Silken Robe | +3 | 45g |
| `chainmail` | Chainmail | +5 | 80g |

### High-Tier Equipment (Ruins Drops / Grimstone Only)

| Name | Type | ATK/DEF | Notes |
|:--|:--|:--|:--|
| Longsword | Weapon | +4 ATK, d8 | |
| Steel Blade | Weapon | +5 ATK, d10 | |
| Resonance Staff | Weapon | +5 ATK, d10 | Mage/Cleric |
| Resonance Bow | Weapon | +6 ATK, d10 | |
| Aeridorian Axe | Weapon | +7 ATK, d12 | |
| Void Blade | Weapon | +9 ATK, d12 | |
| Half Plate | Armor | +7 DEF | |
| Full Plate | Armor | +9 DEF | |
| Arcane Vestment | Armor | +6 DEF | Mage/Cleric |
| Aeridorian Plate | Armor | +11 DEF | |

### Consumables

| Item Key | Name | Effect | Price |
|:--|:--|:--|:--|
| `bandage` | Bandage | +5 HP | 6g |
| `healing_herb` | Healing Herb | +8 HP | 10g |
| `tonic` | Tonic | +15 HP | 20g |
| `elixir` | Elixir | +30 HP | 50g |

Use with `!rpg use <item_key>`. Works in and out of combat.

---

## Forest Events

Each hunt has a chance to trigger a special encounter instead of a monster. These cost 1 hunt and are resolved entirely by Python. Kaia narrates.

**Event rates by location:**

| Location | Chance |
|:--|:--|
| Whisperwood Edge | 20% |
| Trade Road | 18% |
| Whisperwood Deep | 15% |
| Aeridor Ruins | 10% |

### Event List

**✨ Sylvan Sprites**
Small luminous creatures heal 4–11 HP. If you're already at full health, they regard you curiously and drift off. +5–10 XP.

**🎪 Moogle Sighting**
A small white creature with a red pom-pom. 50/50: drops 10–30 Gil, or grants +1 hunt today. Either way it says "kupo" and leaves.

**🌿 Injured Silvani Hunter**
A Silvani is trapped at the treeline. Help them (WIS check). Success: healing herbs and XP. Failure: XP only. The Silvani never speak. It's cultural.

**🧙 The Old Man's Riddle**
An old man at the path's edge. INT check DC 8. Pass: choice of XP, Gil, or a Sharp Mind buff. Fail: 5 XP and mild embarrassment. He was expecting it.

**🐦 Chocobo Tracks**
Three-toed prints in the mud. Following them takes time but reveals a shortcut. +1 hunt today. +12 XP. The chocobo is long gone.

**💎 Aeridor Fragment**
A crystal shard half-buried in tree roots. Hums at a frequency felt more than heard. Added to inventory. Sell to Hemlock for 30 Gil. XP scales with level.

**🍄 Gilded Mushroom**
8–23 Gil worth of rare mushrooms growing in shadow. Hemlock will buy them. +8 XP.

**👁️ A Veiled Elder**
One of the pale race, standing in the path as if waiting. They say something that shouldn't be comprehensible. It is. Grants a class-specific buff until next combat.

**🔪 Timid Tonberry**
A small robed figure with a lantern and a chef's knife. It sees you. Its enormous eyes go wide. It runs. Outcomes: dropped coin pouch (60–100 Gil), abandoned knife (equippable), or clean escape. +20–40 XP. You feel, obscurely, like the villain.

**📬 Mognet Delivery**
A moogle hands you a sealed letter with both paws. It is urgent about this. Take it to Oakhaven and use `!rpg deliver` for 25 Gil + 20 XP. +10 XP on accept.

**🔮 Crystal Resonance**
An Aeridorian crystal pulses in the ruin wall. INT check DC 7. Attune: large XP reward (scales with level). Fail: the resonance rejects you. 3–7 HP damage. It was not personal.

---

## NPCs

| NPC | Location | Command |
|:--|:--|:--|
| **Elder Elara** | Oakhaven Town Square | `!rpg talk elara` |
| **Old Man Hemlock** | Hemlock's Store | `!rpg talk hemlock` |
| **Mira** | Stone Hearth Inn | `!rpg talk barkeep` |
| **The Hooded Figure** | Stone Hearth Inn | `!rpg talk hooded_figure` |
| **Watchtower Guard** | The Watchtower | `!rpg talk guard` |

The hooded figure in the corner has not moved in three days. Mira stopped checking.

---

## The Bestiary

Six tiers. One hundred and twenty monsters.

### Tier Guide

| Tier | Symbol | Recommended For |
|:--|:--|:--|
| Trivial | 🔵 | Any level |
| Easy | 🟢 | Level 1+ |
| Medium | 🟡 | Level 4+ |
| Hard | 🟠 | Level 7+ |
| Deadly | 🔴 | Level 10+ |
| Boss | 💀 | Named encounters only |

### Bestiary — Selected Entries

**TRIVIAL**
Goblin · Goblin Guard · Vampire Bat · Flan · Black Flan · Moldwynd · Elf Toad · Killer Bee · Microchu · Sahagin · Stroper · Blood Slime · Crew Dust · Grat · Nutkin · Forest Boar · Snipper · Myconid · Mud Flan · Leaf Bunny · Thorn Lizard · Will-o'-Wisp · Shadow Hound

**EASY**
Skeleton · Zombie · Ghoul · Dire Wolf · Ghost · Black Goblin · Cockatrice · Steel Bat · Gigas · Lizardman · Harpy · Pink Puff · Skull Eater · Sea Snake · Road Bandit

**MEDIUM**
Gargoyle · Ochu · Lamia · Stone Golem · Dhorme Chimera · Dark Wizard · Werewolf · Wyvern · Abductor · Aeridorian Soldier · Manticore · Cray Claw · Mini Satana · Magic Pot · Reflect Mage · Treant · Wind Serpent · Earth Bear · Rogue Alchemist

**HARD**
Tonberry · Malboro · Dark Knight · Iron Giant · Jura Aevis · Magic Dragon · Archeoaevis · Titan · Shadow Dancer · Killer Mantis · Skull Knight · Minotaur · Nachtmahr · Crystelle · Birostris · Page 256 · Veiled Stalker · Soil Ghoul

**DEADLY**
Behemoth · Ancient Dragon · Lich · Adamantoise · Omega · Shinryu · The Accursed Tree · Azulmagia · Necrophobe · Gilgamesh · Apocalypse · Great Behemoth · Shadow Lich · Cactuar · Sand Worm · Atomos

**BOSS**
Elder Treant · Tonberry King · Aeridorian Guardian · The Hooded Figure · Heart of the Whisperwood · Elder Elara (Turned)

> *Cactuar: DEF 20, HP 10. Good luck.*
> *Magic Pot: DEF 30, HP 1. Figure it out.*
> *Page 256: Don't ask.*

---

## Full Command Reference

### Character & World
| Command | Description |
|:--|:--|
| `!rpg` | Open HUD — HP, XP, Gil, location, hunts |
| `!rpg new <Name> <Race> <Class>` | Create your character |
| `!rpg sheet` | View detailed character sheet |
| `!rpg sheet @user` | View another player's sheet |
| `!rpg look` | Kaia narrates your surroundings |
| `!rpg go <location>` | Travel (supports aliases: inn, woods, ruins, tower…) |
| `!rpg go` | List available exits from current location |
| `!rpg map` | Show world map |
| `!rpg calendar` | View current season and upcoming events |
| `!rpg notices` | View world events and duel results |
| `!rpg duel <@user>` | Challenge a player to a non-lethal duel |
| `!rpg accept` | Accept a pending duel challenge |

### Stone Hearth Inn
| Command | Description |
|:--|:--|
| `!rpg rest` | Full HP restore (5 Gil, must be at inn) |
| `!rpg drink` | +3 temporary HP (2 Gil) |
| `!rpg gamble` | Dice game, 10 Gil buy-in |
| `!rpg rumor` | Hear Aethelgard gossip |
| `!rpg talk barkeep` | Speak with Mira |

### Shrine of the Silent Ones
| Command | Description |
|:--|:--|
| `!rpg pray` | Daily blessing — +2 to all rolls on next hunt |
| `!rpg offer <amount>` | Donate Gil for XP (1 per Gil, 20/day cap) |
| `!rpg brew` | Access the alchemy system (at Maren's Hut) |

### The Watchtower
| Command | Description |
|:--|:--|
| `!rpg scout` | Preview monster activity at all hunting grounds (once/day) |
| `!rpg bank` | Access banking (deposit/withdraw) |

### Hemlock's General Store
| Command | Description |
|:--|:--|
| `!rpg shop` | View inventory and prices |
| `!rpg buy <item>` | Purchase an item |
| `!rpg sell <item>` | Sell an item (50% value) |
| `!rpg talk hemlock` | Speak with Hemlock |

### Inventory & Equipment
| Command | Description |
|:--|:--|
| `!rpg inventory` | List all carried items with descriptions |
| `!rpg equip <item>` | Equip weapon or armor from inventory |
| `!rpg use <item>` | Use a consumable |
| `!rpg deliver` | Complete a Mognet letter delivery (in Oakhaven) |

### Combat & Hunting
| Command | Description |
|:--|:--|
| `!rpg hunt` | Fight a random monster at your location (1 hunt) |
| `!rpg attack` | Strike your current target |
| `!rpg flee` | Attempt escape (d20 ≥ 10 succeeds) |
| `!rpg hunts` | Check remaining hunts today |
| `!rpg roll <dice>` | Pure dice roll (d20, 2d6+3, etc.) |

### NPC Dialogue
| Command | Description |
|:--|:--|
| `!rpg talk elara` | Speak with Elder Elara |
| `!rpg talk hemlock` | Speak with Old Man Hemlock |
| `!rpg talk barkeep` | Speak with Mira |
| `!rpg talk hooded_figure` | Speak with the figure in the corner |
| `!rpg talk guard` | Speak with a guard at the Watchtower |

### Reference
| Command | Description |
|:--|:--|
| `!rpg bestiary` | Full monster list with stats |
| `!rpg help` | Quick command list |
| `!rpg notices` | Read the square's notice board |

### Admin Only
| Command | Description |
|:--|:--|
| `!rpg xp <amount> [@user]` | Award milestone XP |
| `!rpg give <item> [@user]` | Grant an item |
| `!rpg heal <amount> [@user]` | Restore HP |
| `!rpg event <description>` | Push a world event to the channel |

---

## Location Aliases

You do not need to type exact location keys. These all work:

| You type | Goes to |
|:--|:--|
| `inn`, `tavern` | Stone Hearth Inn |
| `hemlock`, `store`, `shop` | Hemlock's General Store |
| `shrine` | Shrine of the Silent Ones |
| `tower`, `watchtower` | The Watchtower |
| `forest`, `woods`, `edge` | Whisperwood Edge |
| `deep` | Whisperwood Deep |
| `ruins` | Aeridor Ruins |
| `road` | The Trade Road |
| `town`, `square` | Oakhaven Town Square |

---

## Known Issues & Pending Features

| Status | Item |
|:--|:--|
| 🔴 Pending | Death revival sequence — Kaia narration on blackout |
| 🔴 Pending | Tonberry's Knife not yet equippable |
| 🔴 Pending | Boss encounters not yet triggerable via hunt |
| 🟡 Pending | Grimstone not yet accessible |
| 🟡 Pending | `!rpg use` items inside active combat turn |
| 🔵 Pending | Loot drops from monster kills (pelts, fangs, cores) |
| 🔵 Pending | Poisoned / Weakened conditions from monsters |
| ✅ Done | PvP Duel system (non-lethal) |
| ✅ Done | World State & Reputation mechanics |
| ✅ Done | Notice Board & Banking |

---

## World Notes

The Whisperwood is louder than usual this season.
Something in the ruins has been active since the last full moon.
Hemlock raised the price of elixirs. He won't say why.
Elder Elara looks tired. She always looks tired.
The hooded figure in the corner of the Stone Hearth has not moved in three days. Mira stopped checking.

---

*Aethelgard is a persistent world running inside Kaiacord.*
*Kaia narrates. Python decides. The world doesn't wait for you.*