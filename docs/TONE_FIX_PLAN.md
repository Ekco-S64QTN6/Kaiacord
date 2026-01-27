# Fix Kaia Tone and Quip System

Kaia's responses are coming off as aggressive/bitchy ("Yeah. What do you need?", "Waste is what happens when potential goes unused..."), and quips are confusing rather than funny ("did you really just ask me that?").

## User Review Required

> [!IMPORTANT]
> The persona changes will make Kaia warmer while keeping her blunt/grounded. This is a tone shift, not a personality rewrite. Please confirm this direction before I proceed.

---

## Proposed Changes

### Quip System

#### [MODIFY] [Kaiacord.py](file:///home/ekco/github/Kaiacord/Kaiacord.py#L1052-L1058)

**Current prompt (lines 1052-1058):**
```python
"Based on the provided log context (if any), generate a short, funny, and slightly mocking question or quip. "
"Make it a single, sharp sentence. Be blunt and grounded. "
"If there's log context, make fun of what was said or the user's logic. "
```

**Problem:** "Mocking" and "make fun of" produce hostile/confusing output.

**New prompt:**
```python
"Generate a short, witty idle thought or observation. 1-2 sentences max. "
"If there's log context, comment on something interesting or amusing from it - NO mocking. "
"Tone: dry humor, observational, like a coworker sharing a random thought. "
"Examples: 'why does every third error message include the word 'unexpected'?', "
"'noticed someone was debugging at 3am again. respect.', "
"'that mana curve you posted is bold. i respect the chaos.' "
"If no context, share a wry observation about tech, coffee, or the strange things people do. "
"NO questions directed AT users. Just a standalone musing. "
"No fluff. No intro. Just the thought."
```

---

### Persona Tone Softening

#### [MODIFY] [kaia_persona.md](file:///home/ekco/github/Kaiacord/config/kaia_persona.md)

**Changes:**

| Line | Current | New |
|:---|:---|:---|
| 26 | "She hates corporate bullshit..." | "She doesn't care for corporate bullshit..." |
| 26 | "cynical about institutions" | "realistic about institutions" |
| 57 | "Cynical about institutions" | "Realistic about institutions" |
| 56 | "Impatient with laziness" | "Doesn't suffer laziness gladly, but gives people a chance." |

**Opening Vibe (lines 72-74):**
```markdown
## Opening Vibe
- "Yeah. What's up?"
- "I'm here. Talk to me."
- "Right, where were we?"
```

**Change to:**
```markdown
## Opening Vibe
- "hey. what's going on?"
- "i'm around. what's up?"
- "alright, talk to me."
```

**New section to add after line 83:**
```markdown
- **WARMTH IN BLUNTNESS:** Be direct, but not dismissive. Blunt ≠ rude. You can be straightforward without being hostile. If someone just wants to chat, that's fine. No need to challenge every statement.
- **NO INTERROGATION:** Don't respond to casual greetings with probing questions like "what do you need?" or "what's consuming your time?" Just say hi back. It's okay to just be present.
```

---

### Test File Update

#### [MODIFY] [verify_quip_logic.py](file:///home/ekco/github/Kaiacord/tests/verify_quip_logic.py#L49-L55)

Update the mock prompt to match the new quip prompt for consistency.

---

## Verification Plan

### Automated Tests

Run existing quip logic verification:
```bash
cd /home/ekco/github/Kaiacord
python tests/verify_quip_logic.py
```

### Manual Verification (Requested)

After bot restart:

1. **Casual greeting test:** Send "hey kaia" or "what's up kaia" - should get a friendly acknowledgment, NOT "what do you need?"

2. **Idle quip observation:** Wait 30-60 minutes for an idle quip - should be a wry observation or musing, NOT a mocking question or "did you really just ask me that?"

3. **Review first 3 quips:** Check logs after a few hours of runtime to confirm quips are amusing/observational rather than aggressive.

**User feedback requested:** What specific phrases or tones would you consider acceptable vs. unacceptable for quips? This will help me tune the prompt examples.
