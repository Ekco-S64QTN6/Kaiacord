# Roadmap

What is open, and the call on each. Updated 6 November 2026.

Each item carries a decision: **Yes** (to build), **Watch** (measure before building), **Owner's
call**, or **No** (researched and declined, with the reason). Closed work is in `git log` and the
pull requests.

## To build

| Item | What | Effort | Call |
|:--|:--|:--|:--|
| **Twitch chat** | Kaia in the owner's Twitch chat (IRC over TLS/WebSocket with a bot account's OAuth token). | 1–2 days | Yes, when the owner says go |
| **UV-K5 as a scanner receiver** | The Quansheng UV-K5 alongside or instead of the RTL-SDR. It demodulates inside the radio and sends no IQ, so it needs an audio path (an AIOC, or a cable into a USB sound card). Receive only: Kaia never transmits. | 1 day once the audio path exists | Yes; blocked on hardware |

## Records (`!music records`)

| Item | What | Call |
|:--|:--|:--|
| **Lock check passes far-moved blends** | A blend at 11/16 bars that had to move −122 ms sounded rough; 16% of locked blends move ≥ 0.18 beat. Tighten the acceptance on how far a blend was moved, not only how many bars agree. | Watch, then tighten |
| **One voice at a time** | The mid knob hands the vocals over at the swap, but a voice's presence (2–5 kHz) sits partly in the high band, which the incoming record brings in early. Real separation needs stems. | Watch |
| **Tempo glide audible** | A record stretched 5–6% glides back 0.5% every 8 bars, each a resplice; it can be heard. `music.records_tempo_glide` turns it off. | Owner's call |

## Watch

| Item | What |
|:--|:--|
| **Speaker inversion** | Once, she credited someone else with her own theory. One case; no mechanical cause found. |
| **Invented facts about real works** | Invented song titles and word definitions, defended when corrected. No guard; a fix needs a source to check against. |
| **Scanner carrier lockout** | After a full-minute non-speech hold the scanner ignores ±75 kHz, doubling up to 4 h. With several constant carriers, about 1 MHz can be out of view for hours. |

## Aethelgard

| Item | What | Call |
|:--|:--|:--|
| **More Spine creatures** | The 77 stair guardians now have explicit floor-scaled HP/ATK/DEF and milestone Resonance Ward progression; additional rare spawns per zone would add variety. | Content, optional |
| **Shadowblade endgame damage** | The highest sustained damage per round (crit on 17 with the Voidstep Blade), offset by the Rogue's low HP. | Watch |
| **Board games as real game state** | Tic-tac-toe with Python holding the board, about 2 h. | No — one game asked for in five months |

## Completed since the previous review

| Work | Outcome |
|:--|:--|
| **Aethelgard handler extraction** (PRs #221–#226) | Complete. World, navigation, inventory/equipment, recovery/rest, banking, reference, consumables, gambling, Shrine, scouting, advancement, character creation, detailed sheets, status, and owner-only admin commands have dedicated handlers. `utils/commands/rpg_handler.py` is the public command dispatcher; `utils/ttrpg/rpg_core_handler.py` is the compatibility/dependency-adapter and remaining orchestration layer; no handler-split item remains open. |
| **Reciprocal owner-admin locking** (PR #236) | `!rpg give` and `!rpg heal` acquire caller and target action locks in sorted UID order; self-target actions acquire the one shared lock once. |
| **PDF extraction isolation** (PR #237) | Existing per-worker resource ceilings now sit behind a process-wide two-worker semaphore; saturated requests wait at most one second and fail closed. |
| **Observation digest quote validation** (PR #238) | Quotes must match one speaker turn; unmatched delimiters fail validation; a single quote-free retry is revalidated before a digest is stored or broadcast. |
| **RPG interaction regression coverage** (PRs #239–#241) | Added status-selector ownership/duplicate/stale-state tests, rest-refusal tests, and detailed-sheet pet/DEF/other-player-view tests. |
| **Proactive and handler cleanup** (PRs #242–#243) | Added punctuation-only opener-dedupe coverage, including same-channel suppression and cross-channel isolation, and removed the unused duplicate `_names()` helper from the core adapter. |
| **Dream continuity I/O isolation** (PR #254) | Continuity reads and updates now run in worker threads from async dream flows; updates retain atomic replacement through the shared write helper. |
| **Dispatcher and test-guidance documentation** (PR #248) | Corrected public dispatcher versus compatibility-adapter ownership, aligned the default no-external-services pytest selection with the `network` marker, removed stale test counts, and clarified handler, PDF-ingestion, and CI boundaries. |
| **RPG navigation name-matching regression** (PR #249) | Added whole-word/phrase-boundary coverage and verified that the public look adapter resolves a partial target name without matching embedded substrings. |

## Validation still blocked

- **Live Discord Aethelgard smoke test (#180):** remains open pending an operator-approved run against the deployed bot, a designated test guild/channel, and a disposable character. CI cannot prove live gateway readiness, actual command/component delivery, permissions, or deployed recovery. The issue records the required safe run evidence.
- **Deployed Linux PDF validation (#206):** automated Linux worker resource-enforcement coverage is merged (#207–#208); the production host's kernel, Python build, cgroup/container memory budget, and a representative PDF test result still need to be captured on that host. GitHub-hosted CI does not substitute for this evidence.

## Declined, with the reason

| Item | Why not |
|:--|:--|
| **Retrain the LoRA** | The dataset is rebuilt and gated, but about half the kept replies still read as an assistant. Review it with `finetune/01g_review.py` first, then train overnight. |
| **Domain-routed retrieval** | Measured over 17 real questions: routing by domain fixed nothing the current fusion missed. |
| **Chat ahead of queued GPU work** | 2 of 371 chat turns waited for the GPU, the longest 14 s. Revisit if `!sysmon` shows a queue while people talk. |
| **Smaller book chunks** | 512-token chunks beat 1,024 by one question in sixteen; not worth a full rebuild. |
| **Hash manifest for the index** | Would save seconds of CPU embedding a day. |
| **Durable facts from old logs** | The one step that loses information, for no measured gain. |
| **Forum self-recognition** | Kaia replying to threads about herself as a bystander. Build it (about 2 h) when the forum integration is switched back on. |
| **Persona line on concision** | `kaia_persona.md` is the owner's to edit; not measured as the cause of her clipped cadence. |
