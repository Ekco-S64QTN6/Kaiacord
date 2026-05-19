import sys
sys.path.append("/home/ekco/github/Kaiacord")
from utils.core.response_filter import BotSpeakFilter

original = "it's a human construct, rooted in a desire for predictability and control."
filtered = BotSpeakFilter.harden(original)
print("Original:", original)
print("Filtered:", filtered)
