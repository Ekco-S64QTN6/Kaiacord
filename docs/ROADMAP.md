# Roadmap

What is open, and the call on each. Updated 25 November 2026.

Each item carries a decision: **Yes** (to build), **Watch** (measure before building), **Owner's
call**, or **No** (researched and declined, with the reason). Closed work is in `git log`.

## To build

| Item | What | Effort | Call |
|:--|:--|:--|:--|
| **Twitch chat** | Kaia in the owner's Twitch chat (IRC over TLS/WebSocket with a bot account's OAuth token). | 1–2 days | Yes, when the owner says go |
| **UV-K5 as a scanner receiver** | The Quansheng UV-K5 alongside or instead of the RTL-SDR. It demodulates inside the radio and sends no IQ, so it needs an audio path (an AIOC, or a cable into a USB sound card). Receive only: Kaia never transmits. | 1 day once the audio path exists | Yes; blocked on hardware |
| **Clause excision fragments** | Four shapes still survive in logged sentences (none sent recently): a cut that leaves a clause ending on "for", "to" or "why", or fuses "it's" onto the next clause. `excision_broke_grammar` should keep the original for them. | 1–2 h | Yes, next; measure over the logged matches first |
| **Her self-written notes in the analyst register** | The identity stream, impressions, anchors and beliefs she writes overnight use the vocabulary her persona bans, and they are injected every turn. The fix is in the dream and impression writing prompts. | 2 h | Yes, on the owner's word |
| **Verdicts on a member's state of mind** | Asked by one member to assess another, she judged a real person's mental state. The dream rule against diagnosing people does not cover live replies; it needs a grounding fact, not another negative instruction. | 1–2 h | Yes; the owner words it |

## Records (`!music records`)

**Owner-confirmed north star:** Kaia must become an expert, creative DJ who can build an hour-long
set with musical taste and storytelling. Technical alignment is necessary but insufficient: a
perfectly locked transition can still be boring, crowded or emotionally wrong. Beat/key/phrase
checks are guardrails, not an artistic score. The full product bar and capability target are in
[records-and-booth.md](03-architecture/records-and-booth.md).

Implementation sequence (keep these independently reviewable):

1. [#408 — invalidate record caches by audio identity](https://github.com/Ekco-S64QTN6/Kaiacord/issues/408) ties every derived record artifact (profiles, envelopes, ticks/grids, graph edges, loudness gain and booth waveforms) to the actual audio content, not path/mtime alone.
2. [#404 — cached phrase-level musical-state profiles](https://github.com/Ekco-S64QTN6/Kaiacord/issues/404) builds the evidence layer by extending `songmap` on top of correct cache identity.
3. [#405 — full-set musical arcs and transition intent](https://github.com/Ekco-S64QTN6/Kaiacord/issues/405) consumes those profiles; it must not equate technical lock with artistic quality.
4. [#403 — professional booth/mixer parity](https://github.com/Ekco-S64QTN6/Kaiacord/issues/403) supplies the real hardware/control primitives; it can progress alongside the analysis/planner work.
5. [#406 — composable DJ skills and phrase scheduler](https://github.com/Ekco-S64QTN6/Kaiacord/issues/406) composes only the actions the active mixer actually supports.
6. [#407 — records-mode listener requests](https://github.com/Ekco-S64QTN6/Kaiacord/issues/407) routes intent to the active records session without changing Strudel behavior.
7. [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402) remains the parent acceptance bar: real-crate full-set listening and independent assessment of musicality, not only passing technical tests.


**#405 implementation boundary (merged in PR #411):** the first profile-guided set-planning layer
ranks only already-measured graph edges, compares approximate exit/entry phrase evidence, applies
soft recent-role pacing preferences, and records separate technical/musical/arc explanations in
`graph.json`. A cluttered option is deferred only when another measured option exists; this is
not yet a live wait-for-the-next-phrase execution policy. Missing profiles fall back to the existing
rank. The lead/midrange and other feature curves remain proxies, not vocal/stem/percussion truth.
Real-crate listening and independent assessment have not been performed here and remain mandatory
before any claim that the sets sound better. `#402` remains the acceptance parent.

**#407 implementation boundary (merged in PR #412):** listener requests are routed to the active
records session without resolving Strudel while records mode is playing. Explicit booth track-path
requests remain separate from musical direction. The first supported direction set is more/less
bass, darker/brighter, build/drop and calmer/harder; vocal/acapella and percussion/drum detection
are deliberately unsupported. A latest-wins one-shot preference expires after 15 minutes and
steers only a later autonomous pick. It may move a candidate ahead of the baseline only when
cached phrase evidence supports the requested direction; missing, weak or contrary evidence
preserves the existing set order. It does not change the currently playing deck or claim an
audible effect. A request received during an in-flight pick is deferred to the following pick.
Unit tests cover routing, request lifecycle and preference ranking, not audible DJ quality.
Real-crate listening and independent assessment remain under `#402`.

**#406 implementation boundary (branch in progress):** the first bounded skill catalog now
uses only existing mixer controls: counted build/drop solo EQ moves, explicit no-op breakdown/groove
choices, the legacy phrase-EQ fallback, the existing blend headroom/upper-band/air actions, and
the planner's existing finite echo-out. Solo actions compile from cached phrase profiles on a
latest-track-wins worker and use source-time coordinates even when a deck is stretched; blend
actions compile before plan publication. The renderer evaluates only a bounded action list and
ramps. Manual lane changes claim ownership and ease Kaia's action out; KAIA MIX hands back.
This does not implement #403's missing PFL, loops, jog/pitch bend or general FX, and does not
claim scratches, stutters or vocal/percussion recognition. No real-crate audition or blind
listening evaluation has been performed here; #402 remains the acceptance parent.

| Item | What | Call |
|:--|:--|:--|
| **Expert DJ judgment and set storytelling** | Replace compatibility-first selection as the definition of quality with a musical decision process: understand the records' structure and musical roles, choose the right moment, account for vocals/hooks/density/energy/tension/release, plan the full hour's pacing and contrast, and evaluate what actually sounds. Kaia must sometimes wait, reject a technically valid blend, cut, contrast or choose an unexpected but coherent partner. | Yes — owner-confirmed; [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402) |
| **Composable expert DJ skill library** | Build real, explainable and safely executable skills: beat/phase work, pitch rides, cues, loops/rolls, cue/beat juggling, genuine scratches, phrase cuts, long/short blends, drop and breakdown swaps, vocal/acapella overlays, call-and-response, mashups, filters, FX, stutters, repeats, backspins, brakes and genre-aware technique. No cosmetic controls or fake tricks. | Yes — part of [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402) |
| **Professional booth/mixer parity** | Real PFL/cue mix, hot and memory cues, loops/rolls, live jog/pitch bend, configurable crossfader behavior and an actual bounded FX bus; test real browser interactions. | Yes — [#403](https://github.com/Ekco-S64QTN6/Kaiacord/issues/403) |
| **Dashboard test-selection coverage** | Select `test_dj_dashboard.py` for dashboard Python changes, map the booth asset to meaningful browser tests, and test control interactions rather than CSS strings alone. | Yes — [#401](https://github.com/Ekco-S64QTN6/Kaiacord/issues/401) |
| **Audible musicality acceptance** | Use real local crates and independent/blind human listening to assess full-set pacing, contrast, breakdown timing, vocal overlays, clutter, surprise and purposeful effects. Unit tests and beat-lock metrics alone cannot establish that the mix is good. | Yes — mandatory acceptance for [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402) |
| **Far-moved blends want ears** | A blend moved 0.18 beat or more now needs 0.8 of the shared-kick bars (and four) behind it, and one at the edge of the search is refused. The thresholds come from one blend heard as rough and the journal's numbers: a few far moves that still pass want listening to. The pair graph is measured again (`METHOD` 5) the next time a set starts. | Watch |
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
