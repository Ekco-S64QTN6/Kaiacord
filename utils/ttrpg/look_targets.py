"""
Hardcoded look-at targets per location — `!rpg look at <thing>`
Provides immersive flavor text when players inspect specific objects at locations.
"""

LOCATION_LOOK_TARGETS = {
    "shrine": {
        "flame": (
            "🔥 **The Flame**\n\n"
            "You hold your hand near it. It is warm — but only just. Not the heat of a torch. Something older.\n"
            "The flame tilts toward you as you approach. Not away. Toward.\n\n"
            "You study it longer than you meant to. There's a pattern in the way it moves — three interlocked spirals, "
            "repeating, as if it's trying to show you something.\n\n"
            "*The pattern is familiar in the way things are familiar before you understand why.*\n\n"
            "🔍 **You've studied the Flame.** Something about the pattern stays with you. "
            "*(Acquired: Flame-mark — you'll recognize the symbol if you see it again.)*"
        ),
        "altar": (
            "⛩️ **The Altar**\n\n"
            "A single slab, perfectly level. Warmer than the air around it.\n"
            "When you press your palm flat against it, you feel something low. Like a note held too long to be music.\n\n"
            "On the underside of the altar's edge, nearly invisible: carved text in Old Aeridorian.\n"
            "You can't read it fully, but three words repeat in different forms:\n\n"
            "> *flame — stone — silence*\n\n"
            "The same three words appear in a ring around the base, each accompanied by a flame-spiral glyph.\n\n"
            "🔍 **You've read the Altar inscription.** "
            "*The three-flame seal appears elsewhere. You'd know it if you found it.*"
        ),
        "names": (
            "📜 **The Carved Names**\n\n"
            "Thousands of them. Some have dates. Some only names. Short phrases — *Beloved. Unbroken. Remembered. Gone too soon.*\n"
            "You stop at one name. You don't know it. But looking at it makes your chest feel strange."
        ),
        "carvings": (
            "📜 **The Carvings**\n\n"
            "Every stone surface is covered. The oldest names are barely legible beneath newer ones.\n"
            "Someone has been adding names recently. The chisel marks are fresh.\n\n"
            "Near the base of the central pillar, half-hidden by the altar cloth: "
            "a phrase in Old Aeridorian, untranslated, carved deeper than the rest.\n"
            "Whatever it says, someone cared enough to make it permanent."
        ),
        "offering bowl": (
            "🫙 **The Offering Bowl**\n\n"
            "A shallow stone bowl, black with age. Old offerings sit in it — a bent copper coin, a tooth, dried flowers.\n"
            "The flame burns from the center, untouched by any of it.\n"
            "*Something of value, placed here, tends to be acknowledged.*"
        ),
        "bowl": (
            "🫙 **The Offering Bowl**\n\n"
            "A shallow stone bowl, black with age. Old offerings sit in it — a bent copper coin, a tooth, dried flowers.\n"
            "The flame burns from the center, untouched by any of it."
        ),
        "stones": (
            "🪨 **The Standing Stones**\n\n"
            "Five stones, each twice your height. Every surface carved. Epitaphs.\n"
            "*Here the honored sleep. The fire watches. Do not wake them.*"
        ),
        "stone": (
            "🪨 **The Standing Stones**\n\n"
            "Five stones, each twice your height. Every surface carved. Epitaphs.\n"
            "*Here the honored sleep. The fire watches. Do not wake them.*"
        ),
        "seal": (
            "🔶 **The Seal**\n\n"
            "You weren't looking for it. But once you see it, you can't unsee it — "
            "carved into the flagstone directly beneath the flame-bowl:\n"
            "three interlocked spirals in a circle.\n\n"
            "The same symbol. The same three-flame pattern.\n\n"
            "You've seen this in the dungeon shrine rooms. You've seen it here.\n"
            "They're connected.\n\n"
            "*Elder Elara would know what this means. So would the Hooded Figure, probably.*"
        ),
    },
    "stone_hearth": {
        "fire": (
            "🔥 **The Hearth**\n\n"
            "The fire has been going since before Mira worked here. She inherited it lit.\n"
            "A figure in the corner stares into it. Has been staring for an hour."
        ),
        "hearth": (
            "🔥 **The Hearth**\n\n"
            "The fire has been going since before Mira worked here. She inherited it lit.\n"
            "A figure in the corner stares into it. Has been staring for an hour."
        ),
        "hooded_figure": (
            "👤 **The Hooded Figure**\n\n"
            "Sits in the corner. Face never visible. Speaks rarely.\n"
            "He doesn't look at you. But somehow you feel seen."
        ),
        "corner": (
            "👤 **The Corner**\n\n"
            "Something cloaked sits very still in the far corner.\n"
            "You're not sure how long it's been there."
        ),
        "notice": (
            "📋 **Posted Notices**\n\n"
            "• Caravan work, high road — ask Mira\n"
            "• Grimstone steel prices up — third month running\n"
            "• Someone's dog is missing. Brown. Answers to nothing."
        ),
        "bar": (
            "🍺 **The Bar**\n\n"
            "Mira keeps it clean. The ale is cold. The stew is hot.\n"
            "That's all she promises. It's enough."
        ),
        "bard": (
            "🎵 **Caelindra**\n\n"
            "She's in the far corner with a lute and a mostly-full tankard. "
            "Watching the room with the professional calm of someone who has been paid to watch rooms.\n\n"
            "She's been playing the same melody for the last twenty minutes. "
            "Nobody's asked her to stop. Nobody's asked her to continue.\n"
            "She seems content with that arrangement.\n\n"
            "*`!rpg talk bard` to hear what she's working on.*"
        ),
        "lute": (
            "🎵 **The Lute**\n\n"
            "Old. The varnish is worn through in the spots where her hand holds the neck. "
            "The tuning pegs are different woods — replacements over years.\n\n"
            "The sound it makes is out of proportion to how tired it looks."
        ),
    },
    "hemlocks_store": {
        "shelves": (
            "🏺 **The Shelves**\n\n"
            "Cluttered by a logic only Hemlock understands. Dried herbs, iron rivets, three kinds of rope.\n"
            "Something sealed in wax on the top shelf. You can't identify it. He won't say."
        ),
        "back room": (
            "🚪 **The Back Room**\n\n"
            "The door is closed. Something moves behind it.\n"
            "Hemlock doesn't acknowledge that you looked."
        ),
        "clock": (
            "🕰️ **The Clock**\n\n"
            "A gear-driven clock on the far wall. Keeps perfect time.\n"
            "You don't know where he got it. You don't know how he winds it."
        ),
        "shelf": (
            "🔒 **The Sealed Container**\n\n"
            "Wax-sealed. Heavy. Labeled in a script you don't recognize.\n"
            "Hemlock clears his throat without looking up from the counter. "
            "You stop looking at it."
        ),
    },
    "aeridor_ruins": {
        "crystals": (
            "💎 **The Crystals**\n\n"
            "Crystalline formations that don't catch light — they absorb it.\n"
            "The ground hums faintly if you stand still. You're not sure it's the ground.\n\n"
            "The three-flame pattern is faintly visible in the crystal lattice. "
            "It's everywhere in here, once you know to look for it.\n\n"
            "*Something in the lattice is different today. A secondary resonance — "
            "artificial, imposed. A lock. Someone used Aeridorian principles to seal the Trade Road.*\n\n"
            "*(If you're on the right quest, you might know how to break it.)*"
        ),
        "carvings": (
            "📜 **Aeridorian Carvings**\n\n"
            "Not decorative. Instructional. Warnings, you think.\n"
            "You can't read Aeridorian. But something about the shapes makes you step back.\n\n"
            "One symbol repeats more than others: three interlocked spirals.\n"
            "You've seen it before. At the Shrine in Oakhaven."
        ),
        "ruins": (
            "🏚️ **The Ruins**\n\n"
            "Stone older than memory. Architecture that doesn't follow logic you know.\n"
            "Walls at angles that shouldn't hold. They've been holding for a thousand years."
        ),
        "seal": (
            "🔶 **A Stone Seal**\n\n"
            "Set into the floor of an antechamber. Three interlocked spirals — "
            "the same pattern from the Shrine flame in Oakhaven.\n\n"
            "There's a shallow depression in the center. The size of a palm.\n\n"
            "*It's waiting for something. Or someone who knows what it means.*"
        ),
    },
    "whisperwood_edge": {
        "trees": (
            "🌲 **The Treeline**\n\n"
            "The forest begins here — abruptly, as if it decided.\n"
            "No birdsong. The underbrush shifts when you're not looking directly at it."
        ),
        "path": (
            "🌿 **The Path**\n\n"
            "A thin trail worn into the earth. Old. Rarely used, recently.\n"
            "Something large came through here. The bent twigs haven't sprung back yet."
        ),
        "tracks": (
            "🐾 **Tracks**\n\n"
            "Multiple sets. Mostly deer — then not deer.\n"
            "Something with too many toes pressed deep into the mud. They lead deeper in and don't come back."
        ),
        "light": (
            "💡 **Something Glowing**\n\n"
            "There. Between the trees. A pale light, low to the ground.\n"
            "It doesn't flicker the way fire does. It pulses.\n\n"
            "When you move toward it, it stays the same distance away."
        ),
    },
    "whisperwood_deep": {
        "light": (
            "🌑 **The Dark**\n\n"
            "The canopy closes overhead. The light goes green. Then less than green.\n"
            "Something gave off faint light a moment ago. There's nothing there now."
        ),
        "sounds": (
            "👂 **The Sounds**\n\n"
            "The deep forest is not quiet. It's the wrong kind of loud.\n"
            "Things moving that aren't moving for you."
        ),
        "pattern": (
            "🔶 **A Pattern on the Bark**\n\n"
            "Carved into a massive oak. Old enough that the bark has grown around the edges of the cuts.\n"
            "Three interlocked spirals.\n\n"
            "The same symbol from the Shrine. The same symbol from the ruins.\n"
            "*This forest is older than Aeridor. And it remembers.*"
        ),
    },
    "oakhaven": {
        "notice_board": (
            "📋 **The Notice Board**\n\n"
            "Layered papers, some rain-warped.\n"
            "• REWARD: 40 gil — proof of the bog creature's death (see Elder Elara)\n"
            "• MISSING: Three sheep from Aldric's farm. East pasture.\n"
            "• The Garrison has withdrawn. Travel in groups."
        ),
        "tricklebrook": (
            "💧 **The Tricklebrook**\n\n"
            "A stream running under the bridge planks. Cold and clear.\n"
            "Elara has mentioned the boundary moved. The stream looks the same. You're not sure that's reassuring."
        ),
        "well": (
            "⛲ **The Well**\n\n"
            "Stone. Old. The bucket rope has been replaced recently — the new rope is still bright.\n"
            "Someone left a copper coin on the lip of the well. It's still there.\n\n"
            "*In Aeridorian tradition, coins left at water sources were offerings to resonance pathways beneath the earth.*\n"
            "Whether this person knew that is unclear."
        ),
    },
    "herbalists_hut": {
        "herbs": (
            "🌿 **The Herbs**\n\n"
            "Silver moss. Blood thistle. Dire root. Honey sap.\n"
            "Sister Maren has catalogued them precisely. The labels are in her own shorthand. You can read enough."
        ),
        "vials": (
            "⚗️ **The Vials**\n\n"
            "Rows of stoppered glass. Some cloudy, some clear, some colors you can't name.\n"
            "Maren notices you looking. 'Don't touch the blue ones,' she says. That's all she says."
        ),
        "notes": (
            "📓 **Maren's Notes**\n\n"
            "Open on the worktable. Dense handwriting, diagrams of plant structures, "
            "margin notes in a different hand — older, shakier.\n\n"
            "A page is dog-eared. The heading: *'On the interaction between Aeridorian resonance and living tissue.'*\n\n"
            "*You close the notebook. Maren is watching you close it.*"
        ),
    },
    "housing_district": {
        "lane": (
            "🛤️ **The Lane**\n\n"
            "A well-trodden dirt path lined with small plots of land. Some are just post-and-rope, others have sturdy fences.\n"
            "Smoke from a dozen hearths hangs low in the air. It's the most domestic place in Oakhaven."
        ),
        "gardens": (
            "🌿 **The Gardens**\n\n"
            "Neat rows of soil, some sprouting with the strange, vibrant herbs used in Sister Maren's brewing.\n"
            "You see blood thistle, honey sap, and silver moss all growing here. "
            "It shouldn't be possible for them to thrive in the same soil. But they do."
        ),
        "barnaby": (
            "🪑 **Barnaby**\n\n"
            "Barnaby is currently wrestling with a particularly stubborn piece of oak. He seems to be winning.\n"
            "Sawdust is permanently settled in his eyebrows. He doesn't seem to mind."
        ),
        "pip": (
            "🐾 **Pip**\n\n"
            "Pip is surrounded by a small cloud of hovering moogles and at least three cats of varying levels of fluffiness.\n"
            "They aren't technically selling the animals — they're 'finding them homes'. For a fee."
        ),
        "plots": (
            "🏡 **The Plots**\n\n"
            "Small staked-out areas. Each has a sign with a name. Some are ornate, some are just charcoal on a plank.\n"
            "People are building things here. Persistent things."
        ),
    },

}
