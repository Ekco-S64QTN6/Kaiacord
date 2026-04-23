LOCATION_DATA = {
    "oakhaven": {
        "name": "Oakhaven Town Square",
        "short": "The muddy square at the heart of OakHaven. The Tricklebrook "
                 "gurgles somewhere under the bridge planks.",
        "exits": ["stone_hearth", "hemlocks_store", "shrine",
                  "watchtower", "oakhaven_bank", "whisperwood_edge", "trade_road", "housing_district"],
        "atmosphere": "grey, damp, watchful. The smell of woodsmoke and wet earth.",
    },
    "stone_hearth": {
        "name": "The Stone Hearth Inn",
        "short": "OakHaven's only inn. Low beams, a fire that's always lit, "
                 "ale that's always warm. Mira keeps the peace.",
        "exits": ["oakhaven"],
        "atmosphere": "smoky, close, warm. Voices kept low.",
        "services": {"rest": 5, "ale": 2, "meal": 3},
    },
    "hemlocks_store": {
        "name": "Hemlock's General Store",
        "short": "Cluttered shelves, the smell of dried herbs and iron. "
                 "Hemlock knows where everything is, somehow.",
        "exits": ["oakhaven"],
        "atmosphere": "dim, organized chaos, the tick of a clock somewhere.",
    },
    "shrine": {
        "name": "Shrine of the Silent Ones",
        "short": "Crumbling stone. Ancient carvings worn smooth. "
                 "Someone left fresh flowers this morning.",
        "exits": ["oakhaven", "herbalists_hut"],
        "atmosphere": "quiet, oddly still. The forest sounds stop at the threshold.",
        "blessing": "passive_wis_plus_1",
    },
    "watchtower": {
        "name": "The Watchtower",
        "short": "Rickety stairs. A view of the Whisperwood canopy. "
                 "Two bored guards who know more than they let on.",
        "exits": ["oakhaven"],
    },
    "whisperwood_edge": {
        "name": "Edge of the Whisperwood",
        "short": "The treeline. Where OakHaven's certainty ends. "
                 "Light filters strange here. The birds are too loud.",
        "exits": ["oakhaven", "whisperwood_deep"],
        "hunting": True,
        "recommended_level": 1,
        "density": 1,
        "dist_mult": 1.0,
    },
    "whisperwood_deep": {
        "name": "Whisperwood Deep",
        "short": "Proper forest dark. The canopy closes overhead. "
                 "You can hear things moving that aren't moving for you.",
        "exits": ["whisperwood_edge", "aeridor_ruins"],
        "hunting": True,
        "recommended_level": 4,
        "density": 2,
        "dist_mult": 1.25,
    },
    "aeridor_ruins": {
        "name": "Aeridor Ruins",
        "short": "Stone older than memory. Crystalline formations that catch "
                 "no light. The ground hums faintly if you stand still.",
        "exits": ["whisperwood_deep"],
        "hunting": True,
        "recommended_level": 7,
        "density": 3,
        "dist_mult": 1.5,
        "lore_events": True,
    },
    "trade_road": {
        "name": "The Trade Road",
        "short": "Rutted dirt heading north. Good sight lines. "
                 "That doesn't mean it's safe.",
        "exits": ["oakhaven", "caravan", "grimstone"],
        "hunting": True,
        "recommended_level": 2,
        "density": 1,
        "dist_mult": 1.1,
    },
    "grimstone": {
        "name": "Grimstone",
        "short": "A mining town built into the Spine's rock face. Grey stone, narrow streets, coal dust, and the smell of iron. The Ironclad Guild owns it — in every sense of the word.",
        "exits": ["trade_road", "rusty_pick", "ironclad_office", "assay_office", "pells_depot", "spine_of_the_world"],
        "atmosphere": "utilitarian, damp, perpetually grey. The hammers never fully stop. The air smells of metal and old smoke.",
        "recommended_level": 15,
        "locked_until_quest": "grimstone_path",
    },
    "rusty_pick": {
        "name": "The Rusty Pick",
        "short": "Grimstone's only inn. Low ceilings, bad light, and Spinefire — a local brew that tastes like it was aged in regret. Marta keeps the peace. Rook keeps the corner.",
        "exits": ["grimstone"],
        "atmosphere": "smoky, low-ceilinged, quieter than it should be. The conversations stop when the door opens.",
        "services": {"rest": 8, "spinefire": 3, "meal": 4},
    },
    "ironclad_office": {
        "name": "Ironclad Guild Office",
        "short": "Overseer Valdric's domain. Neat desk, neat paperwork, a smile that arrives a fraction of a second too late.",
        "exits": ["grimstone"],
        "atmosphere": "clean, formal, slightly too warm. The kind of room that was designed for one kind of conversation.",
    },
    "assay_office": {
        "name": "The Assay Office",
        "short": "Where ore is weighed and recorded. Senna's workspace. The numbers here are not what the Guild thinks they are.",
        "exits": ["grimstone"],
        "atmosphere": "cramped, precise. Scales everywhere. The smell of metal and old paper.",
    },
    "pells_depot": {
        "name": "Old Pell's Depot",
        "short": "Hardware, rope, lamp oil, provisions. Old Pell knows the Spine better than the Guild does, and has made arrangements accordingly.",
        "exits": ["grimstone"],
        "atmosphere": "cluttered, specific, oddly well-stocked for a town this remote.",
    },
    "spine_of_the_world": {
        "name": "The Spine of the World",
        "short": "Mountain passes and deep cave systems above the treeline. Stone that hasn't seen sun in centuries. The things that live here are old, patient, and enormous.",
        "exits": ["grimstone"],
        "atmosphere": "cold, vast, alien. Wind that cuts. Rock that hums. The sense of being watched from above and below simultaneously.",
        "hunting": True,
        "recommended_level": 15,
        "density": 3,
        "dist_mult": 1.75,
    },
    "herbalists_hut": {
        "name": "Sister Maren's Hut",
        "short": "A small lean-to tucked behind the shrine. The air is thick with the scent of drying herbs.",
        "exits": ["shrine"],
        "atmosphere": "earthy, quiet, medicinal.",
        "brewing_allowed": True,
    },
    "oakhaven_bank": {
        "name": "Oakhaven Bank",
        "short": "A sturdy stone building near the square. A heavy wooden box with a complex lock sits behind the counter.",
        "exits": ["oakhaven"],
        "atmosphere": "secure, formal, smells of old paper and copper.",
    },
    "caravan": {
        "name": "Corvus Road Trading Co.",
        "short": "A large, colorful wagon with unfolding wooden panels showing tier III gear. The smell of exotic spices and fine leather hangs in the air.",
        "exits": ["trade_road"],
        "atmosphere": "bustling, wealthy, temporary. The merchant watches everyone with a keen eye.",
    },
    "housing_district": {
        "name": "Oakhaven Housing District",
        "short": "A quiet lane east of the square. Smoke from hearths, the smell of turned earth. People built lives here.",
        "exits": ["oakhaven", "tricklebrook_pond"],   # Only exit is back to Oakhaven — player plots are sub-locations
        "atmosphere": "settled, domestic, oddly peaceful. The Whisperwood is visible but distant.",
        "hunting": False,
    },
    "tricklebrook_pond": {
        "name": "Tricklebrook Pond",
        "short": "A still, deep pool where the Tricklebrook widens before plunging into the caverns. Old Gregor sits on a stump, watching his bobber.",
        "exits": ["housing_district"],
        "atmosphere": "contemplative, quiet, smelling of algae and damp earth.",
        "hunting": False,
    },
}

def resolve_location(query: str) -> str:
    """Fuzzy match a location name or alias to a location key."""
    if not query:
        return ""
    q = query.lower().strip()
    
    aliases = {
        "hemlocks":        "hemlocks_store",
        "hemlock":         "hemlocks_store",
        "store":           "hemlocks_store",
        "shop":            "hemlocks_store",
        "inn":             "stone_hearth",
        "tavern":          "stone_hearth",
        "pub":             "stone_hearth",
        "shrine":          "shrine",
        "whisperwood":     "whisperwood_edge",
        "forest":          "whisperwood_edge",
        "woods":           "whisperwood_edge",
        "edge":            "whisperwood_edge",
        "deep":            "whisperwood_deep",
        "ruins":           "aeridor_ruins",
        "road":            "trade_road",
        "town":            "oakhaven",
        "square":          "oakhaven",
        "oakhaven":        "oakhaven",
        "watchtower":      "watchtower",
        "watchers":        "watchtower",
        "tower":           "watchtower",
        "bank":             "oakhaven_bank",
        "herbalist":        "herbalists_hut",
        "hut":              "herbalists_hut",
        "caravan":          "caravan",
        "merchant":         "caravan",
        "housing":          "housing_district",
        "district":         "housing_district",
        "plots":            "housing_district",
        "home":             "housing_district",
        "pond":             "tricklebrook_pond",
        "fish":             "tricklebrook_pond",
        "tricklebrook":     "tricklebrook_pond",
        "grimstone":        "grimstone",
        "mining town":      "grimstone",
        "ironclad":         "grimstone",
        "pick":         "rusty_pick",
        "rusty pick":   "rusty_pick",
        "rusty_pick":   "rusty_pick",
        "valdric":      "ironclad_office",
        "guild office": "ironclad_office",
        "assay":        "assay_office",
        "pell":         "pells_depot",
        "depot":        "pells_depot",
        "spine":        "spine_of_the_world",
        "mountains":        "spine_of_the_world",
    }
    
    if q in aliases:
        return aliases[q]
        
    if q in LOCATION_DATA:
        return q # ensure validity as key
        
    for key, data in LOCATION_DATA.items():
        name = data.get("name", "")
        if not isinstance(name, str):
            name = str(name)
        if q in key or q in name.lower():
            return key
            
    return ""
