import json

# 1. Update npc_registry.py
with open("utils/ttrpg/npc_registry.py", "r", encoding="utf-8") as f:
    npc_data = f.read()

# Add deity topics to NPCs
elara_topic = '"Aerthis does not reward the devout for faith. He rewards them for action. There\'s a distinction.",\n            "On Morvenna\'s Eve, she walks Aethelgard like anyone else. She says she just wants to see how it\'s going.",'
hemlock_topic = '"Vethran doesn\'t distinguish between a soldier and a mercenary. He only distinguishes between those who held and those who ran.",\n            "Corvus blesses no one. He arranges circumstances. What you do with them is your prayer.",'
gregor_topic = '"Thornax doesn\'t answer prayers. He answers behavior. Prove you belong, and the forest opens.",'
maven_topic = '"Sylvara doesn\'t grant power. She tears open the door to it and steps aside.",'

npc_data = npc_data.replace(
    '"The Aeridor constructs are becoming more active. They weren\'t dormant — they were waiting.",',
    '"The Aeridor constructs are becoming more active. They weren\'t dormant — they were waiting.",\n            ' + elara_topic
)

npc_data = npc_data.replace(
    '"Gregor doesn\'t talk much. That\'s not a flaw. That\'s a feature.",',
    '"Gregor doesn\'t talk much. That\'s not a flaw. That\'s a feature.",\n            ' + hemlock_topic
)

npc_data = npc_data.replace(
    '"Best bait is whatever they\'re biting. Worst bait is whatever you brought.",',
    '"Best bait is whatever they\'re biting. Worst bait is whatever you brought.",\n            ' + gregor_topic
)

npc_data = npc_data.replace(
    '"I met a man from Aeridor once. He tasted of copper and regret.",',
    '"I met a man from Aeridor once. He tasted of copper and regret.",\n            ' + maven_topic
)

with open("utils/ttrpg/npc_registry.py", "w", encoding="utf-8") as f:
    f.write(npc_data)

# 2. Update class_advancement.py
with open("utils/ttrpg/class_advancement.py", "r", encoding="utf-8") as f:
    class_data = f.read()

class_replacements = {
    '"You kneel at the Shrine and feel something ancient acknowledge you. The flame burns white for a moment.",': '"Aerthis acknowledges your oath. The flame at the Shrine burns white-blue.",',
    '"The flame at the Shrine gutters when you approach. You take that as a yes.",': '"Morvenna is watching. The flame at the Shrine burns amber-black.",',
    '"Something old in the deep wood approves. The trees do not move but you sense them watching.",': '"Thornax approves. The Whisperwood breathes with you.",',
    '"The Aeridor resonance sings at a frequency you now understand. You wish you didn\'t.",': '"Sylvara tears open the door for you. The resonance sings aloud.",',
    '"The Shrine of the Silent Ones goes very quiet when you make your choice.",': '"Morvenna welcomes your final lesson. The Shrine goes dead quiet.",',
    '"The shadows don\'t just hide you anymore. They recognize you.",': '"Corvus nods from the laughing road. You are a trick of the shadows.",',
    '"The Shrine doesn\'t acknowledge you, but that\'s fine. You don\'t answer to them.",': '"Corvus blesses the favorable odds. The Shrine may ignore you, but the road remembers.",',
    '"The Shrine flares brightly. You are an instrument of the Silent Ones.",': '"Aerthis hands down the absolute law. You are his unbending instrument.",',
}

for old, new in class_replacements.items():
    class_data = class_data.replace(old, new)

with open("utils/ttrpg/class_advancement.py", "w", encoding="utf-8") as f:
    f.write(class_data)

