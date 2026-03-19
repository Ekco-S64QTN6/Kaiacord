"""
Hardcoded look-at targets per location — `!rpg look at <thing>`
Provides immersive flavor text when players inspect specific objects at locations.
"""

LOCATION_LOOK_TARGETS = {
    "shrine": {
        "flame":          "🔥 **The Flame**\n\nYou hold your hand near it. It is warm — but only just. Not the heat of a torch. Something older.\nThe flame tilts toward you as you approach. Not away. Toward.\nYou pull back. The flame settles.",
        "altar":          "⛩️ **The Altar**\n\nA single slab, perfectly level. Warmer than the air around it.\nWhen you press your palm flat against it, you feel something low. Like a note held too long to be music.",
        "names":          "📜 **The Carved Names**\n\nThousands of them. Some have dates. Some only names. Short phrases — *Beloved. Unbroken. Remembered. Gone too soon.*\nYou stop at one name. You don't know it. But looking at it makes your chest feel strange.",
        "carvings":       "📜 **The Carvings**\n\nEvery stone surface is covered. The oldest names are barely legible beneath newer ones.\nSomeone has been adding names recently. The chisel marks are fresh.",
        "offering bowl":  "🫙 **The Offering Bowl**\n\nA shallow stone bowl, black with age. Old offerings sit in it — a bent copper coin, a tooth, dried flowers.\nThe flame burns from the center, untouched by any of it.\n*Something of value, placed here, tends to be acknowledged.*",
        "bowl":           "🫙 **The Offering Bowl**\n\nA shallow stone bowl, black with age. Old offerings sit in it — a bent copper coin, a tooth, dried flowers.\nThe flame burns from the center, untouched by any of it.",
        "stones":         "🪨 **The Standing Stones**\n\nFive stones, each twice your height. Every surface carved. Epitaphs.\n*Here the honored sleep. The fire watches. Do not wake them.*",
        "stone":          "🪨 **The Standing Stones**\n\nFive stones, each twice your height. Every surface carved. Epitaphs.\n*Here the honored sleep. The fire watches. Do not wake them.*",
    },
    "stone_hearth": {
        "fire":           "🔥 **The Hearth**\n\nThe fire has been going since before Mira worked here. She inherited it lit.\nA figure in the corner stares into it. Has been staring for an hour.",
        "hearth":         "🔥 **The Hearth**\n\nThe fire has been going since before Mira worked here. She inherited it lit.\nA figure in the corner stares into it. Has been staring for an hour.",
        "hooded_figure":  "👤 **The Hooded Figure**\n\nSits in the corner. Face never visible. Speaks rarely.\nHe doesn't look at you. But somehow you feel seen.",
        "corner":         "👤 **The Corner**\n\nSomething cloaked sits very still in the far corner.\nYou're not sure how long it's been there.",
        "notice":         "📋 **Posted Notices**\n\n• Caravan work, high road — ask Mira\n• Grimstone steel prices up — third month running\n• Someone's dog is missing. Brown. Answers to nothing.",
        "bar":            "🍺 **The Bar**\n\nMira keeps it clean. The ale is cold. The stew is hot.\nThat's all she promises. It's enough.",
    },
    "hemlocks_store": {
        "shelves":        "🏺 **The Shelves**\n\nCluttered by a logic only Hemlock understands. Dried herbs, iron rivets, three kinds of rope.\nSomething sealed in wax on the top shelf. You can't identify it. He won't say.",
        "back room":      "🚪 **The Back Room**\n\nThe door is closed. Something moves behind it.\nHemlock doesn't acknowledge that you looked.",
        "clock":          "🕰️ **The Clock**\n\nA gear-driven clock on the far wall. Keeps perfect time.\nYou don't know where he got it. You don't know how he winds it.",
    },
    "aeridor_ruins": {
        "crystals":       "💎 **The Crystals**\n\nCrystalline formations that don't catch light — they absorb it.\nThe ground hums faintly if you stand still. You're not sure it's the ground.",
        "carvings":       "📜 **Aeridorian Carvings**\n\nNot decorative. Instructional. Warnings, you think.\nYou can't read Aeridorian. But something about the shapes makes you step back.",
        "ruins":          "🏚️ **The Ruins**\n\nStone older than memory. Architecture that doesn't follow logic you know.\nWalls at angles that shouldn't hold. They've been holding for a thousand years.",
    },
    "whisperwood_edge": {
        "trees":          "🌲 **The Treeline**\n\nThe forest begins here — abruptly, as if it decided.\nNo birdsong. The underbrush shifts when you're not looking directly at it.",
        "path":           "🌿 **The Path**\n\nA thin trail worn into the earth. Old. Rarely used, recently.\nSomething large came through here. The bent twigs haven't sprung back yet.",
        "tracks":         "🐾 **Tracks**\n\nMultiple sets. Mostly deer — then not deer.\nSomething with too many toes pressed deep into the mud. They lead deeper in and don't come back.",
    },
    "whisperwood_deep": {
        "light":          "🌑 **The Dark**\n\nThe canopy closes overhead. The light goes green. Then less than green.\nSomething gave off faint light a moment ago. There's nothing there now.",
        "sounds":         "👂 **The Sounds**\n\nThe deep forest is not quiet. It's the wrong kind of loud.\nThings moving that aren't moving for you.",
    },
    "oakhaven": {
        "notice_board":   "📋 **The Notice Board**\n\nLayered papers, some rain-warped.\n• REWARD: 40 gil — proof of the bog creature's death (see Elder Elara)\n• MISSING: Three sheep from Aldric's farm. East pasture.\n• The Garrison has withdrawn. Travel in groups.",
        "tricklebrook":   "💧 **The Tricklebrook**\n\nA stream running under the bridge planks. Cold and clear.\nElara has mentioned the boundary moved. The stream looks the same. You're not sure that's reassuring.",
    },
    "herbalists_hut": {
        "herbs":          "🌿 **The Herbs**\n\nSilver moss. Blood thistle. Dire root. Honey sap.\nSister Maren has catalogued them precisely. The labels are in her own shorthand. You can read enough.",
        "vials":          "⚗️ **The Vials**\n\nRows of stoppered glass. Some cloudy, some clear, some colors you can't name.\nMaren notices you looking. 'Don't touch the blue ones,' she says. That's all she says.",
    },
}
