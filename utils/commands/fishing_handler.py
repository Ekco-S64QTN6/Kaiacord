"""
fishing_handler.py — Aethelgard Fishing System Discord UI
===========================================================
Handles all fishing interactions: casting, reeling, shop, leaderboard.
Location: tricklebrook_pond
NPC: Old Gregor (sells bait/poles, buys fish)
"""
import asyncio
import discord
import secrets
from datetime import datetime

from utils.ttrpg.broadcast import (
    log_world_event as _log_world_event,
    broadcast_world_event as _broadcast_world_event
)
from utils.infrastructure.logging.kaia_logger import log_error
from utils.ttrpg.character_manager import load, save
from utils.ttrpg.fishing import FISH, BAIT, POLES, BAG_UPGRADES, DEFAULT_BAG_CAPACITY, get_time_of_day
from utils.ttrpg.fishing_engine import (
    roll_catch,
    calculate_catch_value,
    add_to_fishing_bag,
    sell_fishing_bag,
    get_bag_summary,
    update_world_records,
    get_world_records,
    get_fishing_leaderboard,
    get_fishing_stats_embed_fields,
    get_bite_wait_time,
    get_reel_window,
)
from utils.ttrpg.calendar import get_season

POND_COLOR = 0x3a8fc1  # deep pond blue

CATEGORY_EMOJIS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "mythic": "🔴",
}

GREGOR_LINES = [
    "*Old Gregor doesn't look up from his line.*\n\"The fish know. When you're desperate, they know.\"",
    "*He nods at the water.*\n\"Thirty years I've been trying to catch the one at the bottom. Haven't managed yet. But I know it's there.\"",
    "*He re-ties his hook without looking.*\n\"Patience isn't a virtue here. It's the only currency that works.\"",
    "*He glances at your pole.*\n\"That'll do. Won't do well, but it'll do.\"",
    "*He spits in the water.*\n\"The ones that get away are always the heaviest. That's just how it works.\"",
    "*Gregor taps the side of his nose.*\n\"Early morning. That's when the good ones move. Most people can't be bothered.\"",
    "*He doesn't turn from the water.*\n\"The Tricklebrook connects to something older than the ruins. I don't fish at midnight anymore. Not after last time.\"",
    "*He holds up a scarred hand.*\n\"The Pale King did this. Forty years ago. I saw it once more, last winter. It looked the same.\"",
    "*Gregor scratches his beard.*\n\"Crystal bait? Don't use it carelessly. You might catch something that doesn't want to be caught.\"",
    "*He watches your technique critically.*\n\"Less tension on the line. Let it feel natural. The fish knows when you're trying too hard.\"",
]


# ── Fishing Menu View ─────────────────────────────────────────────────────────

class FishingMenuView(discord.ui.View):
    """Main fishing location UI at tricklebrook_pond."""

    def __init__(self, ctx, uid: str, uname: str, is_owner: bool, sheet: dict):
        super().__init__(timeout=180)
        self._ctx = ctx
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._sheet = sheet

        stats = sheet.get("fishing_stats", {})
        pole = stats.get("pole")
        bait = stats.get("bait", "earthworm")
        bait_count = stats.get("bait_count", 0)
        pole_name = POLES.get(pole, {}).get("name", "None") if pole else "None"
        bait_name = BAIT.get(bait, {}).get("name", "Earthworm")

        bag_count = sum(len(v) for v in sheet.get("fishing_bag", {}).values())
        bag_label = f"🐟 Bag ({bag_count})" if bag_count > 0 else "🐟 Bag (empty)"

    @discord.ui.button(label="🎣 Cast", style=discord.ButtonStyle.primary, row=0)
    async def cast_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("```\nnot your rod.\n```", ephemeral=True)
            return
        await interaction.response.defer()
        await _handle_cast(self._ctx, interaction, self._uid, self._uname, self._is_owner)

    @discord.ui.button(label="🐟 Bag", style=discord.ButtonStyle.secondary, row=0)
    async def bag_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        await interaction.response.defer()
        await _handle_check_bag(self._ctx, interaction, self._uid, self._uname, self._is_owner)

    @discord.ui.button(label="🛒 Shop", style=discord.ButtonStyle.secondary, row=0)
    async def shop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if str(interaction.user.id) != self._uid:
            await interaction.followup.send("not yours.", ephemeral=True)
            return
        await _handle_fishing_shop(self._ctx, interaction, self._uid, self._uname, self._is_owner)

    @discord.ui.button(label="🏆 Records", style=discord.ButtonStyle.secondary, row=1)
    async def leaderboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        await interaction.response.defer()
        await _handle_fishing_leaderboard(self._ctx, interaction, self._uid, self._uname, self._is_owner)

    @discord.ui.button(label="💬 Talk Gregor", style=discord.ButtonStyle.secondary, row=1)
    async def gregor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        await interaction.response.defer()
        line = GREGOR_LINES[secrets.randbelow(len(GREGOR_LINES))]
        embed = discord.Embed(
            title="🎣 Old Gregor",
            description=line,
            color=POND_COLOR,
        )
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="📊 My Stats", style=discord.ButtonStyle.secondary, row=1)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        await interaction.response.defer()
        sheet = await load(self._uid)
        if not sheet:
            await interaction.followup.send("No character found.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"🎣 {sheet['character_name']} — Fishing Stats",
            color=POND_COLOR,
        )
        for name, value in get_fishing_stats_embed_fields(sheet):
            embed.add_field(name=name, value=value, inline=True)
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="💰 Sell All Fish", style=discord.ButtonStyle.green, row=2)
    async def sell_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        await interaction.response.defer()
        await _handle_sell_catch(self._ctx, interaction, self._uid, self._uname, self._is_owner)

    async def on_timeout(self):
        pass


# ── Bite View (Reel mechanic) ─────────────────────────────────────────────────

class BiteView(discord.ui.View):
    """
    Shown after a bite is detected.
    Player has reel_window seconds to click Reel It In!
    """

    def __init__(self, ctx, uid: str, uname: str, is_owner: bool,
                 fish_key: str, fish_weight: float, fish_value: int, reel_window: int):
        super().__init__(timeout=reel_window)
        self._ctx = ctx
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._fish_key = fish_key
        self._fish_weight = fish_weight
        self._fish_value = fish_value
        self._reel_window = reel_window
        self._reeled = False
        self._channel = None   # set by caller

    @discord.ui.button(label="🎣 Reel It In!", style=discord.ButtonStyle.danger, row=0)
    async def reel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            await interaction.response.send_message("not your line.", ephemeral=True)
            return
        if self._reeled:
            await interaction.response.send_message("Already reeled.", ephemeral=True)
            return

        self._reeled = True
        self.stop()

        await interaction.response.defer()
        sheet = await load(self._uid)
        if not sheet:
            return

        fish = FISH.get(self._fish_key, {})
        cat = fish.get("category", "common")
        cat_emoji = CATEGORY_EMOJIS.get(cat, "⚪")
        fish_name = fish.get("name", self._fish_key)
        is_world_record = update_world_records(
            self._fish_key, self._fish_weight,
            sheet["character_name"], self._uid
        )

        # Check personal record
        stats = sheet.get("fishing_stats", {})
        prev_record = stats.get("personal_records", {}).get(self._fish_key, {})
        is_personal_record = (
            not prev_record or self._fish_weight > prev_record.get("weight", 0)
        )

        # Broadcast world event for top-tier world records only
        if cat in ("epic", "legendary", "mythic") and is_world_record:
            msg_parts = []
            if is_world_record:
                msg_parts.append("🌍 **NEW WORLD RECORD!**")
            msg_parts.append(f"🎣 **{self._uname}** caught a **{cat_emoji} {fish_name}** ({self._fish_weight:.2f} lbs) at Tricklebrook Pond!")

            msg_text = " ".join(msg_parts)
            await _log_world_event(msg_text)
            
            # Post to main #aethelgard broadcast channel
            embed = discord.Embed(
                description=msg_text,
                color=0x4db3ff
            )
            await _broadcast_world_event(self._ctx, embed)

        sheet = add_to_fishing_bag(sheet, self._fish_key, self._fish_weight, self._fish_value)

        # Consume 1 bait
        fishing_stats = sheet.setdefault("fishing_stats", {})
        bait_count = fishing_stats.get("bait_count", 0)
        if bait_count > 0:
            fishing_stats["bait_count"] = bait_count - 1

        # Check for pole breakage — all poles can snap, per-rod chance
        broke_pole = False
        cur_pole_key = fishing_stats.get("pole")
        if cur_pole_key:
            pole_data = POLES.get(cur_pole_key, {})
            snap_chance = pole_data.get("snap_chance", 5)
            if secrets.randbelow(10000) < snap_chance * 100:
                broke_pole = True
                fishing_stats["pole"] = None  # no pole — must buy a new one

        await save(sheet)

        desc_lines = [
            f"**{cat_emoji} {fish_name}**",
            f"*{fish.get('desc', '')}*",
            f"",
            f"⚖️ Weight: **{self._fish_weight:.2f} lbs**",
            f"💰 Value: **{self._fish_value}g** (in bag)",
        ]
        if broke_pole:
            p_name = POLES.get(cur_pole_key, {}).get("name", "pole")
            desc_lines.append(f"\n💥 **CRACK!** Your **{p_name}** snapped under the strain! Buy a new rod from Gregor.")
        if is_world_record:
            desc_lines.append(f"🌍 **NEW WORLD RECORD!** 🌍")
        elif is_personal_record:
            desc_lines.append(f"🏅 *Personal best for this species!*")

        bag_count = sum(len(v) for v in sheet.get("fishing_bag", {}).values())
        bag_key = fishing_stats.get("bag", "woven_sack")
        bag_cap = BAG_UPGRADES.get(bag_key, BAG_UPGRADES["woven_sack"])["capacity"]
        desc_lines.append(f"\n🐟 Bag: {bag_count}/{bag_cap} fish — sell to Gregor anytime.")

        # Rarity-based colors
        colors = {
            "common": 0x888888, "uncommon": 0x2ecc71, "rare": 0x3498db,
            "epic": 0x9b59b6, "legendary": 0xf1c40f, "mythic": 0xff0000,
        }
        embed = discord.Embed(
            title="🎣 Catch!",
            description="\n".join(desc_lines),
            color=colors.get(cat, POND_COLOR),
        )

        view = FishingMenuView(self._ctx, self._uid, self._uname, self._is_owner, sheet)
        await interaction.followup.send(embed=embed, view=view)

    async def on_timeout(self):
        """Fish escapes when reel window closes."""
        if self._reeled:
            return
        self._reeled = True
        if self._channel:
            escape_lines = [
                "*The line goes slack. The fish is gone.*",
                "*You hesitated. The line snapped to slack. Whatever it was, it's gone.*",
                "*The rod goes still. The fish used that second well.*",
                "*Too slow. It felt the hook and left. Clean.*",
                "*The water settles. Nothing.*",
                "*You got distracted trying to hold your drink. The fish got away, and you spilled some ale on your boots. Tragic.*",
                "*The bare hook snaps out of the water and nearly catches your ear. Gregor chuckles quietly.*",
                "*You sneeze. The tension releases. The fish takes its leave.*",
                "*A dragonfly lands on your rod. By the time you notice the bite, the thief is gone with your bait.*",
                "*The fish spat the hook out. You swear it gave you a condescending look before swimming back into the dark.*",
            ]
            escape_text = escape_lines[secrets.randbelow(len(escape_lines))]
            embed = discord.Embed(
                description=escape_text,
                color=0x888888,
            )
            sheet = await load(self._uid)
            if sheet:
                # Still consume bait on escape
                fishing_stats = sheet.setdefault("fishing_stats", {})
                bait_count = fishing_stats.get("bait_count", 0)
                if bait_count > 0:
                    fishing_stats["bait_count"] = bait_count - 1
                await save(sheet)
                view = FishingMenuView(self._ctx, self._uid, self._uname, self._is_owner, sheet)
            else:
                view = discord.ui.View()
            try:
                await self._channel.send(embed=embed, view=view)
            except Exception:
                pass


# ── Handler Functions ─────────────────────────────────────────────────────────

async def _handle_cast(ctx, interaction: discord.Interaction, uid: str, uname: str, is_owner: bool):
    """Core cast mechanic: validate → cast embed → sleep → bite/miss."""
    sheet = await load(uid)
    if not sheet:
        await interaction.followup.send("No character found.", ephemeral=True)
        return

    if sheet.get("location") != "tricklebrook_pond":
        await interaction.followup.send(
            embed=discord.Embed(
                description="You need to be at **Tricklebrook Pond** to fish.\n`!rpg go tricklebrook_pond`",
                color=0xcc4444,
            )
        )
        return

    stats = sheet.setdefault("fishing_stats", {})
    bait_key = stats.get("bait", "earthworm")
    pole_key = stats.get("pole")
    bait_count = stats.get("bait_count", 0)

    # No pole = can't fish
    if not pole_key or pole_key not in POLES:
        await interaction.followup.send(
            embed=discord.Embed(
                description=(
                    "🎣 **You don't have a fishing rod.**\n"
                    "Visit Old Gregor's shop to buy one.\n\n"
                    "*He gestures at the rack by the post. \"Can't fish with your hands.\"*"
                ),
                color=0xcc4444,
            )
        )
        return

    # Bait always required — no exceptions
    if bait_count <= 0:
        await interaction.followup.send(
            embed=discord.Embed(
                description=(
                    "🪱 **No bait remaining.**\n"
                    "Visit Old Gregor's shop to restock.\n\n"
                    "*\"Nothing bites on an empty hook. Buy some bait.\"*"
                ),
                color=0xcc4444,
            )
        )
        return

    # Bag capacity check
    bag_count = sum(len(v) for v in sheet.get("fishing_bag", {}).values())
    bag_key = stats.get("bag", "woven_sack")
    bag_data = BAG_UPGRADES.get(bag_key, BAG_UPGRADES["woven_sack"])
    bag_cap = bag_data["capacity"]
    if bag_count >= bag_cap:
        await interaction.followup.send(
            embed=discord.Embed(
                description=(
                    f"🐟 **Your {bag_data['name']} is full!** ({bag_count}/{bag_cap})\n"
                    f"Sell your fish to Gregor or upgrade your bag in the shop."
                ),
                color=0xcc4444,
            )
        )
        return

    pole_name = POLES.get(pole_key, {}).get("name", "Birchwood Rod")
    bait_name = BAIT.get(bait_key, {}).get("name", "Earthworm")

    CAST_LINES = [
        f"*{uname} casts the line. The {bait_name} disappears into the dark water.*\n\n*The pond settles.*",
        f"*The lure arcs out and drops with a quiet plunk.*\n\n*Waiting...*",
        f"*The {bait_name} hits the surface and sinks. The line goes taut and still.*",
        f"*{uname} casts out toward the deep part of the pool.*\n\n*Something down there might be interested.*",
        f"*The bait settles into the dark water. The trees around the pond go quiet.*",
        f"*You toss the line with a practiced flick. A frog croaks lazily from the reeds.*",
        f"*The {bait_name} lands perfectly near a cluster of lily pads. Prime real estate.*",
        f"*{uname} swings the rod. The line sails out, cutting through a low-hanging patch of mist.*",
        f"*A perfect cast. Now, the waiting game begins.*",
        f"*You adjust your grip and cast. Gregor nods slightly in approval. Or maybe he just nodded off.*",
        f"*The surface of Tricklebrook reflects the sky. Your {bait_name} breaks the mirror.*",
        f"*A gentle breeze ripples the water as your line sinks into the abyss.*",
    ]
    cast_embed = discord.Embed(
        title=f"🎣 Casting — {pole_name}",
        description=CAST_LINES[secrets.randbelow(len(CAST_LINES))],
        color=POND_COLOR,
    )
    cast_embed.set_footer(text=f"Bait: {bait_name} · Pole: {pole_name}")
    await interaction.followup.send(embed=cast_embed)

    # Wait for bite
    wait_time = get_bite_wait_time(pole_key)
    await asyncio.sleep(wait_time)

    # Resolve catch
    season = get_season()
    hour = datetime.now().hour
    time_of_day = get_time_of_day(hour)
    conditions = sheet.get("conditions", [])

    try:
        fish_key, fish_data, fish_weight = roll_catch(bait_key, pole_key, season, time_of_day, conditions)
    except ValueError:
        # Miss
        MISS_LINES = [
            "*Something touched the bait. Something changed its mind.*\n\nNo catch.",
            "*The line moved. Just once. Then nothing.*",
            "*You felt it. You definitely felt it. But the line came back empty.*",
            "*A ripple. Gone. The pond doesn't explain itself.*",
            "*Whatever it was, it wasn't hungry enough.*",
            f"*You pull the line. Half the {bait_name} is gone. Clever little bastard.*",
            "*A shadow passes under the water, investigates your hook, and slowly swims away.*",
            "*You blink, and the bobber is still perfectly placed. You swear it dipped for a second.*",
            "*Nothing. Not even a nibble. Maybe the Whisperwood is too loud today.*",
            "*You pull your hook up. A clump of wet pondweed is attached to it.*",
            "*A small silver fish swims up, nudges your hook, and darts away in sheer disinterest.*",
            "*Gregor sighs faintly nearby. You probably moved too much.*",
        ]
        miss_embed = discord.Embed(
            description=MISS_LINES[secrets.randbelow(len(MISS_LINES))],
            color=0x888888,
        )
        sheet = await load(uid)
        if sheet:
            # Consume bait on miss
            fishing_stats = sheet.setdefault("fishing_stats", {})
            bait_count = fishing_stats.get("bait_count", 0)
            if bait_count > 0:
                fishing_stats["bait_count"] = bait_count - 1
            await save(sheet)
            view = FishingMenuView(ctx, uid, uname, is_owner, sheet)
        else:
            view = discord.ui.View()
        await interaction.followup.send(embed=miss_embed, view=view)
        return

    # Something bit — show bite alert and reel view
    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
    fish_value = calculate_catch_value(fish_key, fish_weight, cha_mod)
    reel_window = get_reel_window(pole_key)

    cat = fish_data.get("category", "common")
    cat_emoji = CATEGORY_EMOJIS.get(cat, "⚪")

    BITE_LINES = {
        "common":    [
            "The line tugs. Something small.",
            "A familiar nibble on the line. Just a regular fish.",
            "The bobber bobs twice, then under. Time to reel."
        ],
        "uncommon":  [
            "The line dips sharply. Something real.",
            "A solid tug. This one has some fight in it.",
            "The rod twitches with sudden energy!"
        ],
        "rare":      [
            "The rod bends. Something is on that line that wasn't there before.",
            "A heavy pull! The water churns as something struggles.",
            "The line hums with tension. This is a rare catch!"
        ],
        "epic":      [
            "The rod jerks hard. Something large is pulling. Very large.",
            "The reel screams as something massive dives for the bottom!",
            "You plant your feet. This is an epic struggle."
        ],
        "legendary": [
            "The rod *bows*. The water breaks. Something you weren't ready for.",
            "Golden scales flash beneath the surface! A legendary beast is on the line!",
            "The pond erupts! Hold on tight!"
        ],
        "mythic":    [
            "The line screams through the water. The pond itself seems to stop. Something ancient is on your hook.",
            "The sky seems to darken. A mythic leviathan is testing your strength!",
            "Old Gregor stands up abruptly, his pipe falling from his mouth. 'By the Silent Ones...'"
        ],
    }
    bite_text_options = BITE_LINES.get(cat, ["The line moves."])
    bite_text = bite_text_options[secrets.randbelow(len(bite_text_options))]

    bite_embed = discord.Embed(
        title=f"{cat_emoji} Something's On!",
        description=(
            f"*{bite_text}*\n\n"
            f"**Reel it in before it gets away!**\n"
            f"*You have {reel_window} seconds.*"
        ),
        color={
            "common": 0x888888, "uncommon": 0x2ecc71, "rare": 0x3498db,
            "epic": 0x9b59b6, "legendary": 0xf1c40f, "mythic": 0xff0000,
        }.get(cat, POND_COLOR),
    )

    channel = interaction.channel
    reel_view = BiteView(
        ctx, uid, uname, is_owner,
        fish_key, fish_weight, fish_value, reel_window
    )
    reel_view._channel = channel

    await interaction.followup.send(embed=bite_embed, view=reel_view)


async def _handle_check_bag(ctx, interaction: discord.Interaction, uid: str, uname: str, is_owner: bool):
    """Show fishing bag contents."""
    sheet = await load(uid)
    if not sheet:
        return

    total_fish, total_val, lines = get_bag_summary(sheet)
    if not lines:
        embed = discord.Embed(
            title="🐟 Fishing Bag",
            description="*Your bag is empty.*\n\nCast a line to fill it.",
            color=POND_COLOR,
        )
    else:
        embed = discord.Embed(
            title=f"🐟 Fishing Bag — {total_fish} fish (~{total_val}g)",
            description="\n".join(lines[:20]),
            color=POND_COLOR,
        )
        if len(lines) > 20:
            embed.set_footer(text=f"...and {len(lines) - 20} more species. Sell to clear the bag.")
        else:
            embed.set_footer(text="Press 'Sell All Fish' to turn your haul into gil.")

    view = FishingMenuView(ctx, uid, uname, is_owner, sheet)
    await interaction.followup.send(embed=embed, view=view)


async def _handle_sell_catch(ctx, interaction: discord.Interaction, uid: str, uname: str, is_owner: bool):
    """Sell all fish in bag to Gregor."""
    sheet = await load(uid)
    if not sheet:
        return

    if sheet.get("location") != "tricklebrook_pond":
        await interaction.followup.send(
            embed=discord.Embed(
                description="You need to be at **Tricklebrook Pond** to sell to Gregor.",
                color=0xcc4444,
            )
        )
        return

    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
    total_gil, fish_count, summary = sell_fishing_bag(sheet, cha_mod)

    if total_gil == 0:
        embed = discord.Embed(
            description=(
                "*Gregor glances at your empty bag.*\n\n"
                "\"Nothing to sell. Catch something first.\""
            ),
            color=0x888888,
        )
    else:
        await save(sheet)
        GREGOR_BUY_LINES = [
            "*Gregor weighs each fish with practiced hands, making small sounds of approval and disapproval.*\n\n",
            "*He inspects your catch without much expression. A few of them get a nod.*\n\n",
            "*Gregor counts coins without looking at you. That's a good sign.*\n\n",
            "*He lifts a fish by the tail, examines it, places it in the bucket.*\n\n",
        ]
        intro = GREGOR_BUY_LINES[secrets.randbelow(len(GREGOR_BUY_LINES))]
        embed = discord.Embed(
            title="💰 Catch Sold",
            description=(
                f"{intro}"
                f"**{fish_count} fish sold for {total_gil}g**\n\n"
                f"```\n{summary}\n```"
                f"\nYour gil: {sheet['gil']}g"
            ),
            color=0x2ecc71,
        )

    view = FishingMenuView(ctx, uid, uname, is_owner, sheet)
    await interaction.followup.send(embed=embed, view=view)


async def _handle_fishing_shop(ctx, interaction: discord.Interaction, uid: str, uname: str, is_owner: bool):
    """Gregor's bait and pole shop."""
    sheet = await load(uid)
    if not sheet:
        return

    embed, view = _build_fishing_shop_ui(ctx, uid, uname, is_owner, sheet)
    await interaction.followup.send(embed=embed, view=view)


def _build_fishing_shop_ui(ctx, uid: str, uname: str, is_owner: bool, sheet: dict):
    stats = sheet.setdefault("fishing_stats", {})
    current_bait = stats.get("bait", "earthworm")
    current_pole = stats.get("pole")
    bait_count = stats.get("bait_count", 0)
    current_bait_name = BAIT.get(current_bait, {}).get("name", "Earthworm")
    current_pole_name = POLES.get(current_pole, {}).get("name", "None") if current_pole else "None"
    current_bag = stats.get("bag", "woven_sack")
    bag_data = BAG_UPGRADES.get(current_bag, BAG_UPGRADES["woven_sack"])
    bag_count = sum(len(v) for v in sheet.get("fishing_bag", {}).values())

    embed = discord.Embed(
        title="🪣 Gregor's Tackle & Bait",
        description=(
            f"*The old man gestures at the box of supplies by the post.*\n"
            f"\"Take what you need. Pay first.\"\n\n"
            f"**Rod:** {current_pole_name} · **Bait:** {current_bait_name} ×{bait_count}\n"
            f"**Bag:** {bag_data['name']} ({bag_count}/{bag_data['capacity']})\n"
            f"**Your Gil:** {sheet.get('gil', 0)}g"
        ),
        color=POND_COLOR,
    )

    # Bait section
    bait_lines = []
    for k, b in BAIT.items():
        ceiling = b["rarity_ceiling"]
        equipped = "✅ " if k == current_bait else "   "
        bait_lines.append(f"{equipped}**{b['name']}** (×1 pack of 10 for {b['cost'] * 10}g) — up to {ceiling} fish\n*{b['desc']}*")
    embed.add_field(name="🪱 Bait (sold in packs of 10)", value="\n".join(bait_lines), inline=False)

    # Pole section
    pole_lines = []
    for k, p in POLES.items():
        price_str = f"{p['cost']}g"
        equipped = "✅ " if k == current_pole else "   "
        pole_lines.append(f"{equipped}**{p['name']}** ({price_str}) — {p.get('snap_chance', 5)}% break chance\n*{p['desc']}*")
    embed.add_field(name="🎣 Poles (break on use — buy replacements)", value="\n".join(pole_lines), inline=False)

    # Bag section
    bag_lines = []
    for k, bg in BAG_UPGRADES.items():
        if bg["cost"] == 0:
            price_str = "Default"
        else:
            price_str = f"{bg['cost']}g"
        equipped = "✅ " if k == current_bag else "   "
        bag_lines.append(f"{equipped}**{bg['name']}** ({price_str}) — holds {bg['capacity']} fish\n*{bg['desc']}*")
    embed.add_field(name="🐟 Bag Upgrades", value="\n".join(bag_lines), inline=False)

    view = FishingShopView(ctx, uid, uname, is_owner, sheet)
    return embed, view


async def _handle_fishing_leaderboard(ctx, interaction: discord.Interaction, uid: str, uname: str, is_owner: bool):
    """Show fishing leaderboard — world records and top anglers."""
    from utils.ttrpg.character_manager import load_all
    records = get_world_records()

    # Build top anglers — resolve char names from all sheets
    all_sheets = await load_all()
    uid_to_name = {str(s["user_id"]): s["character_name"] for s in all_sheets}
    angler_totals = records.get("angler_totals", {})

    angler_lines = []
    medals = ["🥇", "🥈", "🥉"]
    sorted_anglers = sorted(angler_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (a_uid, count) in enumerate(sorted_anglers):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        name = uid_to_name.get(a_uid, "Unknown Angler")
        angler_lines.append(f"{medal} **{name}** — {count} fish")

    # Build heaviest catches
    world_records = records.get("world_records", {})
    heaviest: list[tuple[str, float, str]] = []
    for fish_key, rec in world_records.items():
        fish = FISH.get(fish_key)
        if not fish:
            continue
        heaviest.append((fish["name"], rec["weight"], rec["holder"]))
    heaviest.sort(key=lambda x: x[1], reverse=True)
    heaviest_lines = []
    for i, (fname, weight, holder) in enumerate(heaviest[:10]):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        heaviest_lines.append(f"{medal} **{fname}** — {weight:.2f} lbs (*{holder}*)")

    # Rarest catches
    species_counts = records.get("species_totals", {})
    rarest_lines = []
    # Sort by rarity category desc, then count asc
    cat_order = {"mythic": 0, "legendary": 1, "epic": 2, "rare": 3, "uncommon": 4, "common": 5}
    rare_entries = []
    for fish_key, count in species_counts.items():
        fish = FISH.get(fish_key)
        if not fish:
            continue
        rare_entries.append((fish["name"], fish["category"], count))
    rare_entries.sort(key=lambda x: (cat_order.get(x[1], 9), x[2]))
    for fname, cat, count in rare_entries[:8]:
        cat_emoji = CATEGORY_EMOJIS.get(cat, "⚪")
        rarest_lines.append(f"{cat_emoji} **{fname}** — caught {count}×")

    embed = discord.Embed(
        title="🏆 Tricklebrook Fishing Records",
        color=POND_COLOR,
    )
    if angler_lines:
        embed.add_field(
            name="🎣 Top Anglers (Total Catches)",
            value="\n".join(angler_lines) if angler_lines else "*No catches recorded.*",
            inline=False,
        )
    if heaviest_lines:
        embed.add_field(
            name="⚖️ Heaviest Catches (World Records)",
            value="\n".join(heaviest_lines) if heaviest_lines else "*No records yet.*",
            inline=False,
        )
    if rarest_lines:
        embed.add_field(
            name="💎 Rarest Catches",
            value="\n".join(rarest_lines) if rarest_lines else "*None recorded.*",
            inline=False,
        )

    if not (angler_lines or heaviest_lines or rarest_lines):
        embed.description = "*No records yet. Be the first to cast a line.*"

    sheet = await load(uid)
    view = FishingMenuView(ctx, uid, uname, is_owner, sheet) if sheet else discord.ui.View()
    await interaction.followup.send(embed=embed, view=view)


# ── Fishing Shop View ─────────────────────────────────────────────────────────

class FishingShopView(discord.ui.View):
    """Buy bait packs, poles, and bag upgrades from Gregor."""

    def __init__(self, ctx, uid: str, uname: str, is_owner: bool, sheet: dict):
        super().__init__(timeout=120)
        self._ctx = ctx
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner

        stats = sheet.setdefault("fishing_stats", {})
        current_bait = stats.get("bait", "earthworm")
        current_pole = stats.get("pole")
        current_bag = stats.get("bag", "woven_sack")

        # Bait select (row 0)
        bait_options = []
        for k, b in BAIT.items():
            cost_10 = b["cost"] * 10
            bait_options.append(discord.SelectOption(
                label=f"{b['name']} ×10 ({cost_10}g)",
                value=k,
                description=b["desc"][:100],
                emoji="✅" if k == current_bait else None,
            ))
        bait_sel = discord.ui.Select(
            placeholder="🪱 Buy bait (10 per pack)...", options=bait_options, row=0
        )

        async def _buy_bait(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            chosen_bait = interaction.data["values"][0]
            bait_data = BAIT[chosen_bait]
            cost = bait_data["cost"] * 10
            s = await load(self._uid)
            if not s:
                return
            if s.get("gil", 0) < cost:
                await interaction.followup.send(
                    f"Not enough gil. {bait_data['name']} ×10 costs {cost}g. You have {s.get('gil',0)}g.",
                    ephemeral=True,
                )
                return
            s["gil"] -= cost
            fs = s.setdefault("fishing_stats", {})
            fs["bait"] = chosen_bait
            fs["bait_count"] = fs.get("bait_count", 0) + 10
            await save(s)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"*Gregor hands over a pack of {bait_data['name']}.*\n\n"
                        f"✅ **{bait_data['name']} ×10** purchased for **{cost}g**.\n"
                        f"Bait count: {fs['bait_count']}. Gil: {s['gil']}g"
                    ),
                    color=0x2ecc71,
                )
            )

        bait_sel.callback = _buy_bait
        self.add_item(bait_sel)

        # Pole select (row 1) — all poles cost gil
        pole_options = []
        for k, p in POLES.items():
            label = f"{p['name']} ({p['cost']}g)"
            pole_options.append(discord.SelectOption(
                label=label[:100],
                value=k,
                description=f"{p.get('snap_chance', 5)}% break · {p['desc'][:80]}",
                emoji="✅" if k == current_pole else None,
            ))
        pole_sel = discord.ui.Select(
            placeholder="🎣 Buy a pole...", options=pole_options, row=1
        )

        async def _buy_pole(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            chosen_pole = interaction.data["values"][0]
            pole_data = POLES[chosen_pole]
            cost = pole_data["cost"]
            s = await load(self._uid)
            if not s:
                return
            if s.get("gil", 0) < cost:
                await interaction.followup.send(
                    f"Not enough gil. {pole_data['name']} costs {cost}g.",
                    ephemeral=True,
                )
                return
            s["gil"] -= cost
            fs = s.setdefault("fishing_stats", {})
            fs["pole"] = chosen_pole
            await save(s)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"*Gregor tests the flex of the rod once before handing it over.*\n\n"
                        f"🎣 **{pole_data['name']}** purchased and equipped.\n"
                        f"*{pole_data['desc']}*\n"
                        f"Gil: {s['gil']}g"
                    ),
                    color=0x2ecc71,
                )
            )

        pole_sel.callback = _buy_pole
        self.add_item(pole_sel)

        # Bag upgrade select (row 2)
        bag_options = []
        for k, bg in BAG_UPGRADES.items():
            if bg["cost"] == 0:
                label = f"{bg['name']} (Default)"
            else:
                label = f"{bg['name']} ({bg['cost']}g)"
            bag_options.append(discord.SelectOption(
                label=f"{label} — {bg['capacity']} fish"[:100],
                value=k,
                description=bg["desc"][:100],
                emoji="✅" if k == current_bag else None,
            ))
        bag_sel = discord.ui.Select(
            placeholder="🐟 Upgrade fishing bag...", options=bag_options, row=2
        )

        async def _buy_bag(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            chosen_bag = interaction.data["values"][0]
            bag_info = BAG_UPGRADES[chosen_bag]
            cost = bag_info["cost"]
            s = await load(self._uid)
            if not s:
                return
            fs = s.setdefault("fishing_stats", {})
            cur_bag_key = fs.get("bag", "woven_sack")
            # Prevent downgrading
            cur_bag_cap = BAG_UPGRADES.get(cur_bag_key, BAG_UPGRADES["woven_sack"])["capacity"]
            if bag_info["capacity"] <= cur_bag_cap:
                await interaction.followup.send(
                    f"You already have a **{BAG_UPGRADES[cur_bag_key]['name']}** ({cur_bag_cap} capacity). That's the same or better.",
                    ephemeral=True,
                )
                return
            if cost > 0 and s.get("gil", 0) < cost:
                await interaction.followup.send(
                    f"Not enough gil. {bag_info['name']} costs {cost}g.",
                    ephemeral=True,
                )
                return
            if cost > 0:
                s["gil"] -= cost
            fs["bag"] = chosen_bag
            await save(s)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"*Gregor nods approvingly at the upgrade.*\n\n"
                        f"🐟 **{bag_info['name']}** — now holds {bag_info['capacity']} fish.\n"
                        f"*{bag_info['desc']}*"
                        + (f"\nGil: {s['gil']}g" if cost > 0 else "")
                    ),
                    color=0x2ecc71,
                )
            )

        bag_sel.callback = _buy_bag
        self.add_item(bag_sel)

        # Sell All button (row 3)
        sell_btn = discord.ui.Button(
            label="💰 Sell All Fish", style=discord.ButtonStyle.green, row=3
        )

        async def _sell_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            await _handle_sell_catch(self._ctx, interaction, self._uid, self._uname, self._is_owner)

        sell_btn.callback = _sell_cb
        self.add_item(sell_btn)

    async def on_timeout(self):
        pass


# ── Main entry points for rpg_handler.py dispatch ────────────────────────────

async def handle_fish_command(ctx, msg, send, rest, uid, uname, is_owner):
    """
    Entry for !rpg fish command.
    Routes to the fishing menu if at the pond, otherwise gives directions.
    """
    sheet = await load(uid)
    if not sheet:
        await msg.channel.send(embed=discord.Embed(
            description="No character found. Create one with `!rpg new`.",
            color=0xcc4444,
        ))
        return

    if sheet.get("location") != "tricklebrook_pond":
        await msg.channel.send(embed=discord.Embed(
            title="🎣 Tricklebrook Pond",
            description=(
                "The pond is east of the Housing District.\n\n"
                "`!rpg go tricklebrook_pond` to travel there."
            ),
            color=POND_COLOR,
        ))
        return

    await _show_fishing_menu(ctx, msg.channel, uid, uname, is_owner, sheet)


async def handle_fish_shop_command(ctx, msg, send, rest, uid, uname, is_owner):
    """Entry Point for Gregor's Shop from RPG UI buttons or !rpg fish shop."""
    sheet = await load(uid)
    if not sheet:
        return
    embed, view = _build_fishing_shop_ui(ctx, uid, uname, is_owner, sheet)
    await send(None, embed=embed, view=view)


async def _show_fishing_menu(ctx, channel, uid: str, uname: str, is_owner: bool, sheet: dict):
    """Send the fishing HUD to the channel."""
    stats = sheet.setdefault("fishing_stats", {})
    if "pole" not in stats:
        stats["pole"] = "birchwood_rod"
        stats["bait"] = "earthworm"
        stats["bait_count"] = 5  # small starter gift
        stats["bag"] = "woven_sack"
        await save(sheet)

    pole_key = stats.get("pole")
    pole_name = POLES.get(pole_key, {}).get("name", "None") if pole_key else "None"
    bait_name = BAIT.get(stats.get("bait", "earthworm"), {}).get("name", "Earthworm")
    bait_count = stats.get("bait_count", 0)
    bag_count = sum(len(v) for v in sheet.get("fishing_bag", {}).values())
    bag_key = stats.get("bag", "woven_sack")
    bag_data = BAG_UPGRADES.get(bag_key, BAG_UPGRADES["woven_sack"])

    season = get_season()
    hour = datetime.now().hour
    time_of_day = get_time_of_day(hour)

    TIME_FLAVOR = {
        "dawn":      "The mist is low on the water. The best hour.",
        "morning":   "Clear morning light. Good for surface fishing.",
        "midday":    "The sun is overhead. Fish are deep.",
        "afternoon": "The light slants golden. Fish are starting to move.",
        "evening":   "The dusk cools the water. Rare things stir.",
        "night":     "Dark. The water is black. Something is always moving at night.",
    }

    embed = discord.Embed(
        title="🎣 Tricklebrook Pond",
        description=(
            f"*{TIME_FLAVOR.get(time_of_day, 'The pond is quiet.')}*\n\n"
            f"**Pole:** {pole_name}\n"
            f"**Bait:** {bait_name} (×{bait_count})\n"
            f"**Bag:** {bag_count}/{bag_data['capacity']} fish\n"
            f"**Season:** {season.title()} · **Time:** {time_of_day.title()}"
        ),
        color=POND_COLOR,
    )
    embed.set_footer(text="Old Gregor sits nearby, not talking. That's normal.")

    view = FishingMenuView(ctx, uid, uname, is_owner, sheet)
    await channel.send(embed=embed, view=view)
