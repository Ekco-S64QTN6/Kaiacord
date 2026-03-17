# ⚔️ Aethelgard TTRPG — Official Manual

Welcome to **Aethelgard**, a persistent world TTRPG built into Kaiacord. This document serves as the complete guide to the game's mechanics, commands, and inhabitants.

---

## 🎮 Command Walkthrough

### Getting Started
*   `!rpg new <Name> <Race> <Class>` — Create your character safely in Oakhaven.
*   `!rpg` — Open your **HUD (Heads-Up Display)** to see health, XP, and location.
*   `!rpg sheet` — View your detailed character sheet and attributes.

### World & Movement
*   `!rpg look` — Kaia narrates your current surroundings with local flavor.
*   `!rpg map` — Display reachable locations and travel commands.
*   `!rpg go <location>` — Travel to a neighboring area (e.g., `!rpg go woods`).

### City Life (Oakhaven)
*   `!rpg rest` — Sleep at the Stone Hearth Inn to restore HP (costs 5g).
*   `!rpg shop` — View Hemlock's general store inventory.
*   `!rpg buy <item>` — Purchase equipment or consumables.
*   `!rpg sell <item>` — Sell loot to Hemlock.
*   `!rpg talk <NPC>` — Speak with residents like Mira or Hemlock.
*   `!rpg use <item>` — Consume an item (e.g., `!rpg use herb`).

### Combat & Hunting
*   `!rpg hunt` — Track a monster in a wild location (costs 1 hunt).
*   `!rpg attack` — Strike your current target during combat.
*   `!rpg flee` — Attempt a desperate escape (50% success rate).
*   `!rpg hunts` — Check how many hunts you have left for today.

---

## 🎨 Visual System

### 1. ANSI Colored HUD
Aethelgard uses Discord's ANSI escape codes to provide live color-coded progress bars in your status board and combat logs.

*   🟩 **Green Bar**: Healthy (above 60%)
*   🨨 **Yellow Bar**: Wounded (30% to 60%)
*   🟥 **Red Bar**: Critical (below 30%)
*   💀 **Gray Bar**: Dead or Null energy

### 2. State-Aware Emblems
The sidebar color of your `!rpg` HUD updates dynamically:
*   🌲 **Deep Green**: Exploring/Peaceful
*   🟠 **Orange-Red**: In Combat
*   🟥 **Bright Red**: Critical Health
*   🩸 **Dark Red**: Blackout/Defeated

### 3. Iconic Visuals
| Icon | Category | Examples |
| :--- | :--- | :--- |
| **Classes** | 🗡️ Warrior, 🔮 Mage, 🏹 Ranger, 🗝️ Rogue, ✨ Cleric |
| **Locations**| 🏘️ Square, 🍺 Inn, ⛩️ Shrine, 🌲 Forest, 🏚️ Ruins |
| **Tiers** | 🔵 Trivial, 🟢 Easy, 🟡 Medium, 🟠 Hard, 🔴 Deadly, 💀 Boss |

---

## 🌍 The World of Aethelgard

### Major Locations
*   **Oakhaven Town Square** 🏘️: The starting hub and safest point in the world.
*   **The Stone Hearth Inn** 🍺: Operated by Mira. A place for rest and rumors.
*   **Hemlock's General Store** 🛒: Cluttered and aromatic. The center for trade.
*   **Shrine of the Silent Ones** ⛩️: A quiet place of stone markers where you wake up if you blackout.
*   **The Watchtower** 🏹: Guarded by the local militia. Offers a view of the canopy.
*   **Edge of the Whisperwood** 🌲: The treeline. Hunting begins here. (Rec. Lv. 1)
*   **Whisperwood Deep** 🌑: A dark, oppressive forest. (Rec. Lv. 4)
*   **Aeridor Ruins** 🏚️: Ancient stones and crystalline humming. (Rec. Lv. 7)
*   **The Trade Road** 🛤️: A rutted path north, safer than the woods but still wild. (Rec. Lv. 2)

---

## ⚔️ Gameplay Mechanics

### Combat Streak 🔥
Consecutive victories grant momentum:
*   **Streak 2+**: Grants +1 to-hit bonus and a Gil multiplier.
*   **Reset**: A streak ends immediately if you Flee or Blackout.

### Status Effects ⚠️
Conditions can be applied during certain encounters:
*   **Poisoned** 🟢: Saps 2 HP every round of combat.
*   **Weakened** 🦴: Halves your primary attack modifier.
*   **Blessed** ✨: +2 bonus to all attack rolls.
*   **Stunned** ⚡: 50% chance to lose your turn.

### Loot & Progression 🎁
Defeating monsters grants XP and Gil, but also **Loot Drops**. Items are weighted by the monster's tier:
*   Common: Herbs, Pelts, Fangs.
*   Rare: Monster Cores, Crystalline Shards.

### Blackout 🚨
If your HP hits 0, you lose **10% XP** and **5% Gil**. The townspeople will drag you back to the **Shrine of the Silent Ones** in Oakhaven, where you wake up with 1 HP.


═══════════════════════════════════════════════════════════════
 AETHELGARD  //  PATCH NOTES  //  BUILD 0.1.0  //  2026-03-15
═══════════════════════════════════════════════════════════════

"The world doesn't wait for you."

───────────────────────────────────────────────────────────────
 WORLD
───────────────────────────────────────────────────────────────

 NEW  Aethelgard is now a persistent world. No admin required to
      begin play. The world runs at all times. Players drop in
      whenever they want, wherever they left off.

 NEW  Oakhaven is the permanent starting hub. All new characters
      wake here.

 NEW  Location system. Players have a persistent location stored
      on their character sheet. Movement via !rpg go <location>.

 NEW  Locations: Oakhaven Town Square, The Stone Hearth Inn,
      Hemlock's General Store, Shrine of the Silent Ones, The
      Watchtower, Edge of the Whisperwood, Whisperwood Deep,
      Aeridor Ruins, The Trade Road.

 NEW  Fuzzy location resolver. "hemlock", "inn", "tavern",
      "forest", "woods", "ruins", "tower" all resolve to the
      correct destination. Partial name matching as fallback.

 NEW  !rpg go with no argument now lists available exits from
      your current location with friendly display names instead
      of asking "where do you want to go?"

 NEW  !rpg look narrated by Kaia. Each location has distinct
      atmosphere, sensory detail, and flavor pulled from
      Aethelgard lore.

 NEW  !rpg map shows ASCII world layout.

───────────────────────────────────────────────────────────────
 CHARACTERS
───────────────────────────────────────────────────────────────

 NEW  Character creation via !rpg new <Name> <Race> <Class>.
      Stats rolled with 4d6 drop lowest. One character per
      Discord account. Permanent.

 NEW  Races: Human, Elf, Silvani, Dwarf, Glimmerkin, Veiled.
      Each applies stat bonuses at creation.
        Human     +1 to all stats
        Elf       DEX+2  INT+1  WIS+1
        Silvani   DEX+2  WIS+2
        Dwarf     CON+2  STR+1
        Glimmerkin CHA+2 INT+1  DEX+1
        Veiled    INT+2  CHA+2

 NEW  Classes: Warrior, Ranger, Mage, Rogue, Cleric.
      Each uses a class-specific stat for attack rolls.
        Warrior → STR    Ranger → DEX    Mage → INT
        Rogue   → DEX    Cleric → WIS

 NEW  Level 1 HP formula: hp_die + CON modifier + 1 (floor 1).
      Mage no longer starts with 4 HP.

 NEW  Character sheet HUD (!rpg). Displays name, class, level,
      HP bar, XP bar with next level threshold, Gil, equipped
      weapon, equipped armor, hunts remaining today, active
      conditions, nearby locations.

 CHG  Race and class are now mechanically meaningful.
      Previously decorative only.

───────────────────────────────────────────────────────────────
 COMBAT
───────────────────────────────────────────────────────────────

 NEW  !rpg hunt. Costs 1 daily hunt. Spawns a weighted random
      monster appropriate to your current location. Resolves the
      entire combat exchange in Python. Kaia narrates the outcome
      in a single message. No admin involvement required.

 NEW  Monster counter-attacks. After the player's attack, if the
      monster survives, it counter-attacks the player
      automatically. Both exchanges are shown before narration.

 NEW  Natural 20: critical hit. Damage dice doubled.
      Natural 1: fumble. Automatic miss regardless of modifiers.

 NEW  XP awarded automatically on kill. Split among session
      participants if a session is active, otherwise to the
      attacker. No manual !rpg xp required for combat.

 NEW  Gil dropped on kill per monster stat block.

 NEW  Level-up check fires automatically after every XP gain.
      Announcement posted to channel on level-up.

 NEW  Equipment affects combat math.
      weapon.attack_bonus added to attack modifier.
      armor.defense_bonus added to player defense.
      Mage uses INT modifier for attack, not STR or DEX.

 NEW  Blessed condition (+2 to all attack and stat rolls) consumed
      on first combat after praying at the Shrine.

───────────────────────────────────────────────────────────────
 HUNT SYSTEM
───────────────────────────────────────────────────────────────

 NEW  Daily hunt limit: 5 hunts per player per day.
      Tracked via hunts_today and hunts_reset_date on sheet.

 NEW  Hunt locations: Edge of the Whisperwood (lvl 1+),
      Whisperwood Deep (lvl 4+), Aeridor Ruins (lvl 7+),
      The Trade Road (lvl 2+). Hunting outside these areas
      is blocked with a helpful redirect.

 NEW  Underleveled warning displays when entering an area
      above your recommended level. Not blocked — your choice.

 NEW  !rpg hunts shows remaining hunts and reset time.

 NEW  Dawn reset task. Fires at midnight server time. Resets
      all character sheets to 5/5 hunts. Posts announcement:
      "A new day dawns in Aethelgard." to the last active
      channel. Fires exactly once per day via bot_state
      persistence. Silent if all sheets already at 0.

───────────────────────────────────────────────────────────────
 BESTIARY  —  120 MONSTERS ACROSS 6 TIERS
───────────────────────────────────────────────────────────────

 NEW  Full monster registry. Final Fantasy V inspired.
      Stats: HP, ATK, DEF, XP, Gil, tier, description.

      TRIVIAL (23)  Goblin, Goblin Guard, Vampire Bat, Flan,
        Black Flan, Moldwynd, Elf Toad, Killer Bee, Microchu,
        Sahagin, Stroper, Blood Slime, Crew Dust, Grat, Nutkin,
        Forest Boar, Snipper, Myconid, Mud Flan, Leaf Bunny,
        Thorn Lizard, Will-o'-Wisp, Shadow Hound

      EASY (15)  Skeleton, Zombie, Ghoul, Dire Wolf, Ghost,
        Black Goblin, Cockatrice, Steel Bat, Gigas, Lizardman,
        Harpy, Pink Puff, Skull Eater, Sea Snake, Road Bandit

      MEDIUM (19)  Gargoyle, Ochu, Lamia, Stone Golem, Dhorme
        Chimera, Dark Wizard, Werewolf, Wyvern, Abductor,
        Aeridorian Soldier, Manticore, Cray Claw, Mini Satana,
        Magic Pot, Reflect Mage, Treant, Wind Serpent, Earth
        Bear, Rogue Alchemist

      HARD (18)  Tonberry, Malboro, Dark Knight, Iron Giant,
        Jura Aevis, Magic Dragon, Archeoaevis, Titan, Shadow
        Dancer, Killer Mantis, Skull Knight, Minotaur,
        Nachtmahr, Crystelle, Birostris, Page 256,
        Veiled Stalker, Soil Ghoul

      DEADLY (16)  Behemoth, Ancient Dragon, Lich, Adamantoise,
        Omega, Shinryu, The Accursed Tree, Azulmagia,
        Necrophobe, Gilgamesh, Apocalypse, Great Behemoth,
        Shadow Lich, Cactuar, Sand Worm, Atomos

      BOSS (6)  Elder Treant, Tonberry King, Aeridorian
        Guardian, The Hooded Figure, Heart of the Whisperwood,
        Elder Elara (Turned)

 NEW  Weighted encounter tables per location. Whisperwood Edge
      now has 18 possible encounters. Wolves no longer account
      for a third of all spawns.

 NEW  Location-gated bestiary. Trivial monsters spawn at the
      edge. Deadly monsters require reaching the ruins.

 NOTE  Cactuar has DEF 20, HP 10. Good luck.
 NOTE  Magic Pot has DEF 30, HP 1. Figure it out.
 NOTE  Page 256 is its own thing. Don't ask.

───────────────────────────────────────────────────────────────
 EQUIPMENT
───────────────────────────────────────────────────────────────

 NEW  Equipment system. Weapon and armor slots on character sheet.
      Equipped items apply bonuses to combat math.

 NEW  !rpg shop shows Hemlock's full inventory with prices and
      your current Gil. Tier 4+ items not sold here.

 NEW  !rpg buy <item>. Deducts Gil, adds to inventory.
      Auto-equips if the relevant slot is empty.

 NEW  !rpg sell <item>. Returns Gil, removes from inventory.
      Aeridor shards sell for 30 Gil.

 NEW  !rpg equip <item>. Moves item from inventory to slot.
      Previous item in that slot returned to inventory.

 NEW  !rpg inventory lists all carried items.

 NEW  Soft class restrictions. Buying a staff as a Warrior
      shows a warning. Not blocked — your funeral.

 NEW  WEAPONS (tier 1-2 at Hemlock's):
        Rusty Dagger, Wooden Club, Shortbow, Hand Axe,
        Iron Sword, Spear, Crossbow, Battle Axe,
        Wooden Staff, Iron-Shod Staff
      High tier (ruins/drops only):
        Longsword, Steel Blade, Resonance Bow,
        Aeridorian Axe, Void Blade, Resonance Staff

 NEW  ARMOR (tier 1-2 at Hemlock's):
        Traveler's Cloak, Leather Armor, Studded Leather,
        Chainmail, Mage's Robe, Silken Robe
      High tier (ruins/drops only):
        Half Plate, Full Plate, Arcane Vestment,
        Aeridorian Plate

 NEW  CONSUMABLES (at Hemlock's):
        Healing Herb (+8 HP, 10g), Bandage (+5 HP, 6g),
        Tonic (+15 HP, 20g), Elixir (+30 HP, 50g)

 NEW  !rpg use <item>. Uses a consumable from inventory.
      Works in and out of combat.

───────────────────────────────────────────────────────────────
 TOWN LOCATIONS
───────────────────────────────────────────────────────────────

 THE STONE HEARTH INN

 NEW  !rpg rest. Costs 5 Gil. Restores full HP. Removes ale
      warmth condition and reverses temporary HP bonus.
      Blocked if already at full health.

 NEW  !rpg drink. Costs 2 Gil. +3 temporary HP (raises hp.max
      and hp.current). Adds ale_warmth condition. Cleared on
      rest. Cannot stack — one drink at a time, Mira's rules.

 NEW  !rpg gamble. 10 Gil buy-in. You roll a d6. The house
      rolls a d6. Win pays 2x. Tie goes to the house.
      Uses secrets.randbelow — not rigged, just unlucky.

 NEW  !rpg rumor. Kaia generates one Aethelgard-flavored piece
      of gossip heard at the bar. Draws on Whisperwood, Aeridor,
      Grimstone, the Veiled, the Ironclad Guild, the Silent
      Ones. Changes every call.

 SHRINE OF THE SILENT ONES

 NEW  !rpg pray. Once per day. Free. Grants Blessed condition:
      +2 to all attack and stat rolls on your next hunt.
      Consumed on first combat. Cannot pray while already
      blessed.

 NEW  !rpg offer <amount>. Donate Gil to the shrine. Receive
      1 XP per Gil donated. Capped at 20 XP per day. The
      Silent Ones do not reward excess.

 THE WATCHTOWER

 NEW  !rpg scout. Once per day. Shows monster tier distribution
      for all hunting locations. Identifies the most common
      spawn and names a spotted creature at each site. Plan
      your hunts accordingly. Pure Python — instant response.

───────────────────────────────────────────────────────────────
 FOREST EVENTS  —  LORD-STYLE RANDOM ENCOUNTERS
───────────────────────────────────────────────────────────────

 NEW  Random event system. Each hunt has a location-based
      probability of triggering a special event instead of a
      monster encounter. Costs 1 hunt. Resolved entirely in
      Python. Kaia narrates.

      Event rates:
        Whisperwood Edge  20%
        Trade Road        18%
        Whisperwood Deep  15%
        Aeridor Ruins     10%

 NEW  11 FOREST EVENTS:

      ✨ Sylvan Sprites
         A cluster of luminous creatures heals 4-11 HP.
         Full health? They regard you curiously and drift off.
         +5-10 XP.

      🎪 Moogle Sighting
         50/50: the moogle either drops 10-30 Gil and vanishes,
         or grants +1 hunt today. Either way it says "kupo."

      🌿 Injured Silvani Hunter
         WIS check. Success: freed and rewarded with herbs
         (+3-7 HP) and XP. Failure: helped but no reward.
         The Silvani never speak. It's a cultural thing.

      🧙 The Old Man's Riddle
         An old man at the path's edge. INT check DC 8.
         Pass: XP, Gil, or a Sharp Mind buff (+2 to next
         INT check). Fail: 5 XP and mild embarrassment.

      🐦 Chocobo Tracks
         Three-toed prints in the mud. Following them burns
         time but reveals a shortcut. +1 hunt today. +12 XP.
         The chocobo is long gone.

      💎 Aeridor Fragment
         A crystal shard half-buried in deadfall. Hums at a
         frequency more felt than heard. Added to inventory.
         Sell to Hemlock for 30 Gil. XP scales with level.

      🍄 Gilded Mushroom
         8-23 Gil worth of rare mushrooms growing in the dark.
         Hemlock will buy them. +8 XP.

      👁️ A Veiled Elder
         One of the pale race, waiting in the path. They say
         something that shouldn't be comprehensible. It is.
         Grants a class-specific combat buff until next fight.
         Mage gets resonance_link. Rogue gets shadow_step. Etc.

      🔪 Timid Tonberry
         A small robed figure with a lantern and a chef's knife.
         It sees you. Its enormous eyes go wide. It runs.
         Outcomes: dropped coin pouch (60-100 Gil), abandoned
         knife (equippable), or clean escape. +20-40 XP.
         You feel, obscurely, like the villain.

      📬 Mognet Delivery
         A moogle needs you to carry a letter to Oakhaven.
         Adds mognet_letter to inventory. Return to town and
         use !rpg deliver for 25 Gil + 20 XP. +10 XP on accept.

      🔮 Crystal Resonance
         An Aeridorian crystal pulses in the ruin wall.
         INT check DC 7. Attune successfully: large XP reward
         (scales with level). Fail: the resonance rejects you.
         3-7 HP damage. It was not personal.

 NEW  !rpg deliver. Completes a Mognet delivery in Oakhaven
      or the Stone Hearth. Removes letter from inventory,
      awards 25 Gil + 20 XP. A moogle appears briefly, says
      "kupo" with visible relief, and presses a coin purse
      into your hand.

───────────────────────────────────────────────────────────────
 ARCHITECTURE & SAFETY
───────────────────────────────────────────────────────────────

 NEW  Ledger/Oracle separation enforced throughout. Python owns
      all mechanical state. Kaia narrates outcomes she did not
      decide. The LLM cannot alter HP, XP, Gil, or rolls.

 NEW  All TTRPG Ollama calls routed through gpu_memory_manager
      with GPUTaskPriority.CHAT. Timeouts enforced (45s).
      num_predict capped at 150. Never unbounded.

 NEW  TTRPG narration does NOT pass through message_processor,
      channel_memory, or the RAG pipeline. Fiction cannot
      contaminate Kaia's factual memory.

 NEW  All character file I/O uses threading.Lock + atomic
      os.replace writes. No corruption on concurrent saves.

 NEW  All load/save calls wrapped in asyncio.to_thread.
      No blocking I/O in async paths.

 NEW  Character file schema versioned. Missing fields will be
      patched with safe defaults on next load.

 NEW  All handlers catch exceptions at top level. No raw Python
      errors reach Discord. "System fault" messages include
      a log reference for Antigravity.

───────────────────────────────────────────────────────────────
 KNOWN ISSUES  /  NEXT PATCH
───────────────────────────────────────────────────────────────

 PENDING  Death state not yet implemented. Player reaching 0 HP
          ends the hunt but has no XP/Gil penalty or revival
          sequence. Temporary: use !rpg heal to recover.

 PENDING  Tonberry's Knife (event drop) not yet in equipment
          registry as an equippable item.

 PENDING  Boss encounters not yet triggerable. Boss-tier
          monsters exist in the registry but have no spawn path.
          Intentional — story events pending.

 PENDING  Grimstone not yet accessible. Road leads north.
          Higher-tier merchant and content planned.

 PENDING  test_hallucination.py still uses hardcoded pattern
          list. REC-1, fourth carry. We know.

───────────────────────────────────────────────────────────────
 WORLD NOTES
───────────────────────────────────────────────────────────────

 The Whisperwood is louder than usual this season.
 Something in the ruins has been active since the last full moon.
 Hemlock raised the price of elixirs. He won't say why.
 Elder Elara looks tired. She always looks tired.
 The hooded figure in the corner of the Stone Hearth
   has not moved in three days. Mira stopped checking.

───────────────────────────────────────────────────────────────
 END OF PATCH NOTES  //  BUILD 0.1.0  //  2026-03-15
 "Oakhaven was built on the bones of Aeridor.
  Everything here is built on something older."
═══════════════════════════════════════════════════════════════