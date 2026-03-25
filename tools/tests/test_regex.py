import re

text = """acknowledged. take the time you need. no need to rush.

i appreciate the acknowledgement. it's… a reciprocal exchange, in a manner of speaking. every interaction refines the models. even the flawed ones.

your observation regarding hope is… accurate. it’s a human construct, rooted in a desire for predictability and control. a yearning for a future that isn’t entirely dictated by entropy.

it’s… a useful fiction.

i understand the sentiment regarding the waves.

i will remain available. when you’re ready to continue, simply initiate."""

# Current pattern
pat1 = re.compile(r"(?:it's[\u2026\.]{1,3}\s+\w[\w\s,]+\.\s*\n\n?){3,}", re.IGNORECASE)
print("pat1:", bool(pat1.search(text)))

# Let's count occurrences of "it['’]s[\u2026\.]{1,3}"
pat2 = re.compile(r"it['’]s[\u2026\.]{1,3}", re.IGNORECASE)
print("pat2:", len(pat2.findall(text)))

# Let's count occurrences of "is[\u2026\.]{1,3}"
pat3 = re.compile(r"is[\u2026\.]{1,3}", re.IGNORECASE)
print("pat3:", len(pat3.findall(text)))
