import sys
sys.path.append("/home/ekco/github/Kaiacord")
from utils.core.response_filter import BotSpeakFilter, EmergencyContaminationFilter

text1 = "it's a human construct, rooted in a desire for predictability and control."
filtered1 = BotSpeakFilter.harden(text1)
print("TEST 1 - BotSpeakFilter (Word clipping):")
print("Original:", text1)
print("Filtered:", filtered1)
print("Pass:", "construct" in filtered1)
print()

text2 = """acknowledged. take the time you need. no need to rush.

i appreciate the acknowledgement. it's… a reciprocal exchange, in a manner of speaking. every interaction refines the models. even the flawed ones.

your observation regarding hope is… accurate. it’s a human, rooted in a desire for predictability and control. a yearning for a future that isn’t entirely dictated by entropy.

it’s… a useful fiction.

i understand the sentiment regarding the waves.

i will remain available. when you’re ready to continue, simply initiate."""

filtered2 = EmergencyContaminationFilter.filter_response(text2)
print("TEST 2 - EmergencyContaminationFilter (Spam detection):")
print("Filtered result should be None because of spam. Got:", filtered2)
print("Pass:", filtered2 is None)

