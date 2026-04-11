NPCS = {
    "elara": {
        "name": "Elder Elara",
        "location": "oakhaven",
        "description": "A weary woman with silver-streaked hair and careful eyes. "
                       "She's carried OakHaven's troubles for two decades.",
        "role": "quest_giver",
        "dialogue_hook": "She watches you with measured caution. Her hands are folded "
                         "on the table. She doesn't waste words.",
        "topics": [
            "The Whisperwood boundary moved twelve feet last night. I measured.",
            "Something came back from the ruins that shouldn't have. I'm handling it.",
            "There's a reason nobody builds east of the Tricklebrook.",
            "Your kind showing up here isn't an accident. I'm still deciding if that's good.",
            "The flame at the Shrine has been burning blue for three nights. It's done that twice before. Neither time was pleasant.",
            "The Aeridor constructs are becoming more active. They weren't dormant — they were waiting.",
            "Aerthis does not reward the devout for faith. He rewards them for action. There's a distinction.",
            "On Morvenna's Eve, she walks Aethelgard like anyone else. She says she just wants to see how it's going.",
            "Whatever your advanced class becomes, use it carefully. Power without restraint is how we got the ruins in the first place.",
        ],
    },
    "hemlock": {
        "name": "Old Man Hemlock",
        "location": "hemlocks_store",
        "description": "Grizzled, taciturn. Sells everything. Talks too much about "
                       "the old days if you let him.",
        "role": "merchant",
        "dialogue_hook": "He doesn't look up from the counter when you enter.",
        "topics": [
            "Back in Aeridor's time this whole store would've been a resonance depot. Not that anyone knows what that means anymore.",
            "I've raised the price on elixirs. Supply chain. Don't ask.",
            "A Silvani came through last week and bought every antidote I had. Left without saying why.",
            "The watchtower guards ordered extra rope. Won't say what for.",
            "Aeridor shards? Yes I'll buy them. No I won't tell you why. That's the deal.",
            "I've been selling to adventurers for forty years. The ones who ask about the deep ruins never come back the same.",
            "You want good armor? Really good armor? Check the dungeon. What Hemlock stocks is comfortable. What the ruins hold is built to survive.",
            "The bard's been filling people's heads with songs again. Lovely voice. Wrong about half the details.",
        ],
    },
    "barkeep": {
        "name": "Mira",
        "location": "stone_hearth",
        "description": "The Stone Hearth's barkeep. Heard everything twice. "
                       "Doesn't judge. Charges fair.",
        "role": "innkeeper",
        "dialogue_hook": "She slides a tankard toward you without being asked.",
        "topics": [
            "The Ironclad Guild men have been in three nights running. Something about the Trade Road.",
            "A traveler from Riverbend said the Silverstream is running black.",
            "Someone left flowers at Elara's door. Nobody's admitting to it.",
            "The hooded figure paid in coins nobody's seen before.",
            "Caelindra's songs are getting darker. She says she's just reflecting the times. I say she knows something.",
            "Three adventurers went into the ruins last week. Two came back. The one who didn't was the strongest of them.",
            "There are stories about what the Shrine flame means when it changes color. I don't repeat them. Bad for business.",
            "You look like you've been through something. Sit. First one's on me.",
        ],
    },
    "hooded_figure": {
        "name": "The Hooded Figure",
        "location": "stone_hearth",
        "description": "A mysterious man who sits in the same shadowy corner every night. His face is always hidden beneath a deep cowl. He speaks rarely, but when he does, people listen.",
        "role": "mystery",
        "dialogue_hook": "The mysterious man remains perfectly still at first. Then, slowly, he shifts his gaze toward you from beneath his cowl.",
        "topics": [
            "The ruins are not ruins.",
            "Aeridor didn't fall. It was absorbed.",
            "Ask Elara what she found at the Shrine before you arrived.",
            "[He says nothing. He doesn't look at you. Somehow you feel seen.]",
            "The three flames on the seal. Fire, stone, silence. You've seen it. Whether you know what it means is a different question.",
            "The dungeon shrine rooms respond to those who've listened at the Oakhaven flame. Not everyone can hear it.",
            "Your choice of path matters. The Aeridor records tracked class designations. Some of those records are still active.",
        ],
    },
    "guard": {
        "name": "Watchtower Guard",
        "location": "watchtower",
        "description": "One of two guards posted at the Watchtower. Bored, observant, and considerably more informed than they let on. They've been watching the Whisperwood for years.",
        "role": "info",
        "dialogue_hook": "He doesn't turn from the window when you approach. His eyes stay on the treeline.",
        "topics": [
            "The canopy's thicker this year. Can't see the smoke from Aeridor anymore.",
            "Saw a light in the deep woods last night. Moved too fast for a lantern.",
            "Hemlock keep asking about the road. Tell him it's as dangerous as ever.",
            "Don't go east. Not today.",
            "We've started double-watching at dawn. Something comes out of the ruins before sunrise. We don't talk about what it looks like.",
            "The dungeon entrance opened up near the east wall three months ago. Before you ask: no, we haven't gone in. We're guards, not adventurers.",
            "Lost two good scouts to the ruins this season. One of them had twenty years of experience. Didn't help.",
        ],
    },
    "maren": {
        "name": "Sister Maren",
        "location": "herbalists_hut",
        "description": "A quiet woman with hands stained by soil and sap. She lives in a small lean-to behind the shrine, tending to her garden of rare herbs.",
        "role": "herbalist",
        "dialogue_hook": "She is carefully pruning a silver-leafed plant as you approach. She doesn't look up, but gestures for you to wait.",
        "topics": [
            "The Silvermoss is blooming early this year. The soil must be changing.",
            "Hemlock keeps asking for more Antidote, but the ingredients are getting harder to find.",
            "Some plants only grow where the forest is thinnest. Others only where it's thickest.",
            "There's a root that only grows in the ruins. I haven't seen it in years.",
            "Blood thistle mixed with honey sap. Basic restorative. The Aeridorian archives called it a 'combat tincture.' Different name, same principle.",
            "Healers and warriors aren't different callings. Both keep people alive. One just does it more directly.",
            "If you're choosing a path forward — Paladin, Shaman, High Priest — come back and speak to me first. Some paths have aftereffects.",
        ],
    },

    # ── NEW: Bard ──────────────────────────────────────────────────────────────
    "bard": {
        "name": "Caelindra",
        "location": "stone_hearth",
        "description": "A traveling bard with ink-stained fingers and eyes that miss nothing. "
                       "Her lute is older than she is. Her songs are local gossip dressed in metaphor.",
        "role": "bard",
        "dialogue_hook": "She's mid-song when you approach. She doesn't stop, but she tracks you "
                         "across the room with those careful eyes.",
        "topics": [
            "Everything that happens in Oakhaven ends up in a song eventually. Whether you want it to or not.",
            "I travel the road between Grimstone and the coast. What I hear, I keep. What I witness, I sing.",
            "The Hooded Figure never tips. But he always listens. That tells you something.",
            "Adventurers make the best subjects. Short lives, dramatic arcs. No offense.",
            "The ruins have a sound at midnight. Not loud. But it's there if you're quiet enough to hear it.",
            "I've been collecting Aeridorian phrases for seven years. Half of them describe things that don't exist anymore. The other half... I'm not certain.",
            "Ask me for a song. I'll make it about you. You might not like what I notice.",
        ],
    },
    "merchant": {
        "name": "Traveling Merchant",
        "location": "caravan",
        "description": "A merchant in sun-bleached silks with a sharp eye for profit and a friendly, if brief, manner.",
        "role": "merchant",
        "dialogue_hook": "He looks up from a ledger, tapping a quill against his chin.",
        "topics": [
            "The road north? It's quiet lately. Too quiet. Even the bandits are hiding. Something's moved into the Aeridor Ruins, and it isn't friendly.",
            "Everything I sell is Tier III. You won't find this level of craftsmanship in a muddy village like Oakhaven. Pick one piece and use it well.",
            "We've traded from the Crystal Peaks to the Southern Sea. Aethelgard is... different. The air tastes like old magic and fresh blood.",
            "One gear item per person. No exceptions. I've got a schedule to keep and a dozen towns waiting for a taste of the masterworks.",
        ],
    },
    "barnaby": {
        "name": "Barnaby",
        "location": "housing_district",
        "description": "A stout man with sawdust permanently in his hair. Sells furniture, decorations, and 'improvements' of dubious necessity with great enthusiasm.",
        "role": "furniture_merchant",
        "dialogue_hook": "He's sanding something when you arrive. He's always sanding something.",
        "topics": [
            "The alchemy bench? Best investment you'll make. Maren charges for the use of her table, you know. She's too polite to say it but she does.",
            "Oak from the Whisperwood edge. I don't take from the deep. The deep keeps its wood.",
            "A throne? You want a throne. Everyone says they don't want a throne. Then they see it.",
            "I made Elder Elara a chair once. She sat in it once. Never came back. I consider it my greatest work.",
            "The Aeridorian tapestry — found that pattern in the ruins. Don't ask how I survived. I have some questions about that myself.",
            "Stone throne's for the keep only. You want to know what it feels like to sit in it before you buy? Can't. That's part of the deal.",
        ],
    },
    "pip": {
        "name": "Pip",
        "location": "housing_district",
        "description": "A small, quiet person who moves like they're trying not to startle something. Always has at least one animal on or near them.",
        "role": "pet_vendor",
        "dialogue_hook": "Pip is sitting cross-legged on the ground when you arrive. A cat is on their lap. A moogle is hovering nearby pretending not to be interested.",
        "topics": [
            "The tonberry? It's docile. I promise. It just holds the knife because that's what tonberries do.",
            "Feed them every day. I can't stress this enough. Every day.",
            "The construct isn't a pet. But it stays. So.",
            "The chocobo chick will imprint on you. That's permanent. Think about whether you want that responsibility.",
            "Moogle's been with me six years. Delivers letters I didn't ask it to. Brings back things I didn't send. I've stopped questioning it.",
            "The sprite came from the Whisperwood edge. It followed me home. The Whisperwood let it, I think. I don't know what that means.",
        ],
    },
    "gregor": {
        "name": "Old Gregor",
        "location": "tricklebrook_pond",
        "description": "An old, quiet fisherman who runs the tackle shop. He has fished Tricklebrook for decades and knows things about the ruins he doesn't discuss.",
        "role": "fisherman",
        "dialogue_hook": "He doesn't look away from his bobber on the water when you approach.",
        "topics": [
            "The fish know when you are desperate. That's why you aren't catching anything.",
            "I've seen things come out of the ruins at midnight. I don't fish here at midnight anymore.",
            "The Pale King broke my line forty years ago. I'm still waiting for him to come back.",
            "Best bait is whatever they're biting. Worst bait is whatever you brought.",
            "Thornax doesn't answer prayers. He answers behavior. Prove you belong, and the forest opens.",
            "Don't pull the line too early. Patience is the only currency here.",
        ],
    },
}

# Add alias
NPCS["caravan"] = NPCS["merchant"]

def get_npc(key: str) -> dict | None:
    return NPCS.get(key.lower())
