# Roadmap

What is open, and the call on each. Updated 10 November 2026.

Each item carries a decision: **Yes** (to build), **Watch** (measure before building), **Owner's
call**, or **No** (researched and declined, with the reason). Closed work is in `git log` and the
pull requests.

## To build

| Item | What | Effort | Call |
|:--|:--|:--|:--|
| **Twitch chat** | Kaia in the owner's Twitch chat (IRC over TLS/WebSocket with a bot account's OAuth token). | 1–2 days | Yes, when the owner says go |
| **UV-K5 as a scanner receiver** | The Quansheng UV-K5 alongside or instead of the RTL-SDR. It demodulates inside the radio and sends no IQ, so it needs an audio path (an AIOC, or a cable into a USB sound card). Receive only: Kaia never transmits. | 1 day once the audio path exists | Yes; blocked on hardware |
| **Clause excision fragments** | Four shapes still survive in logged sentences (none sent recently): a cut that leaves a clause ending on "for", "to" or "why", or fuses "it's" onto the next clause. `excision_broke_grammar` should keep the original for them. | 1–2 h | Yes, next; measure over the logged matches first |
| **Her self-written notes in the analyst register** | The identity stream, impressions, anchors and beliefs she writes overnight use the vocabulary her persona bans, and they are injected every turn. The fix is in the dream and impression writing prompts. | 2 h | Yes, on the owner's word |
| **Verdicts on a member's state of mind** | Asked by one member to assess another, she judged a real person's mental state. The dream rule against diagnosing people does not cover live replies; it needs a grounding fact, not another negative instruction. | 1–2 h | Yes; the owner words it |

## Records (`!music records`)

| Item | What | Call |
|:--|:--|:--|
| **Lock check passes far-moved blends** | A blend at 11/16 bars that had to move −122 ms sounded rough; 16% of locked blends move ≥ 0.18 beat. Tighten the acceptance on how far a blend was moved, not only how many bars agree. | Watch, then tighten |
| **One voice at a time** | The vocals change hands at the swap in the mids and the presence band (to 6 kHz); only the air above rides early. The outgoing's whole vocal still plays over the incoming's held-down one during the ride, and where a record's voice is cannot be measured without stems. | Watch |
| **Mix-out points need ears** | She leaves a record at its outro or last breakdown where a blend locks there, found from loudness curves. The curves find sections, not taste: a few blends at each kind of point want listening to. | Watch |
| **Tempo glide audible** | A record stretched 5–6% glides back 0.5% every 8 bars, each a resplice; it can be heard. `music.records_tempo_glide` turns it off. | Owner's call |

## Aethelgard

| Item | What | Call |
|:--|:--|:--|
| **Long fights at levels 10–12, and the endgame gil sink** | After the 9 Nov progression pass, fights at 10–12 run 9–10 rounds (the overworld HP cap is 14 + 7 a level against ~9 damage a round), and Hemlock's rework was used once in eight months. | Ask players after the wipe; lowering the cap slope is a one-line change to re-measure with `progression_sim.py` |
| **Gameplay rules to confirm** | Rules settled by issues in early November, each documented in the system manual: no overworld co-op assists, a 100-item-type inventory, retired unsupported consumables, five free forest-event rolls a day, re-tuned event rates and boss scaling, floor-scaled Spine guardians, a Shrine blessing that lasts the whole fight, and the RPG stopping on a corrupt world state. | Owner's call; none is a bug |
| **A pending round whose monster is gone** | A recorded overworld round whose monster or session no longer exists would raise on every recovery and block that player's combat. Needs a corrupted session; monsters are only removed by their owner. | Watch |
| **More Spine creatures** | The 77 stair guardians are floor-scaled with milestone Resonance Wards; more rare spawns per zone would add variety. | Content, optional |
| **Shadowblade endgame damage** | The highest sustained damage per round (crit on 17 with the Voidstep Blade), offset by the Rogue's low HP. | Watch |
| **Board games as real game state** | Tic-tac-toe with Python holding the board, about 2 h. | No — one game asked for in five months |

## Watch

| Item | What |
|:--|:--|
| **Prompt-prefix warm-up** | The warm-up caches the persona so a reply can reuse it. On 4–8 Nov 20% of long prompts restored a checkpoint; since the 9 Nov fix (nothing ahead of the persona) 40% have. Keep or drop it after comparing a day with it disabled. |
| **Cadence in what she sends** | Short "the …" fragment runs and "a reminder that" rose sharply in October. History no longer carries the runs and a repeat penalty now applies to her replies; read the live rate (KAIA // OPS, VOICE) over the next days before doing more. |
| **Speaker inversion** | Once, she credited someone else with her own theory. One case; no mechanical cause found. |
| **Invented facts about real works** | Invented song titles and word definitions, defended when corrected. No guard; a fix needs a source to check against. |
| **A message posted back as her reply** | A user's whole message returned verbatim, three times in October and none since. If it recurs, reject a reply that is mostly the user's message. |
| **Anchors that only accumulate** | The old, often-recalled tier is never evicted while a new anchor exists, so it grows; an anchor about something she read tends to last only until the next dream. Count week-old anchors over the next nights. |
| **A file that never indexes** | One permanently failing file would make every refresh report failure and the sweep run every 5 minutes instead of hourly. Not seen; quarantine or skip permanent failures if it shows up. |
| **Scanner carrier lockout** | After a full-minute non-speech hold the scanner ignores ±75 kHz, doubling up to 4 h. With several constant carriers, about 1 MHz can be out of view for hours. |
| **RPG lock-table retention** | `session_manager._action_locks`, `session_manager._chan_locks` and `character_manager._user_locks` keep one lock per ID ever seen. Owner-only `!sysmon` reports their sizes, peaks and contention; collect deployed measurements before designing eviction that cannot replace a held lock or one with waiters. |

## Declined, with the reason

| Item | Why not |
|:--|:--|
| **Retrain the LoRA** | Not yet. The dataset is rebuilt and gated, but about half the kept replies still read as an assistant. Review it with `finetune/01g_review.py` first, then train overnight. |
| **Domain-routed retrieval** | Measured over 17 real questions: routing by domain fixed nothing the current fusion missed. |
| **Chat ahead of queued GPU work** | 2 of 371 chat turns waited for the GPU, the longest 14 s. Revisit if `!sysmon` shows a queue while people talk. |
| **Smaller book chunks** | 512-token chunks beat 1,024 by one question in sixteen; not worth a full rebuild. |
| **Hash manifest for the index** | Would save seconds of CPU embedding a day. |
| **Durable facts from old logs** | The one step that loses information, for no measured gain. |
| **Forum self-recognition** | Kaia replying to threads about herself as a bystander. Build it (about 2 h) when the forum integration is switched back on. |
| **A guard on sentences copied from her last reply** | 8 of 1,961 replies since 20 Sept. |
| **A guard on connective crutches** | "a reminder that", "a testament to": style the persona does not ban; a guard would cut real sentences. |
| **Persona edits** | A line on concision and a stray fragment under its style rules. `kaia_persona.md` is the owner's to edit; neither is measured as a cause. |
