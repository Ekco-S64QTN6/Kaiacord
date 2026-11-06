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

## Completed since 5 November 2026

| Work | Result |
|:--|:--|
| **RPG combat and handler decomposition (#210–#226)** | Dungeon combat phases and the major `!rpg` command areas now have dedicated handler modules. `utils/commands/rpg_handler.py` remains the public command dispatcher; `utils/ttrpg/rpg_core_handler.py` retains compatibility adapters and remaining orchestration. Dedicated handlers cover world information, navigation, inventory/equipment, recovery and inn rest, bank transactions, reference commands, consumables, gambling, Shrine actions, scouting, advancement, character creation, detailed sheets, the status HUD, and owner-only administration. |
| **Owner administration lock ordering (#227 / PR #236)** | `give` and `heal` acquire caller and target user locks in sorted UID order. The adapters own this two-user serialization, so the dispatcher does not pre-hold only the caller lock; self-target actions acquire one lock. |
| **Chat-linked PDF worker limits (#228 / PR #237)** | PDF link extraction retains its per-worker memory, CPU, wall-time, input, page and text ceilings and now admits at most two parser workers process-wide. Waiting for a worker slot is bounded and fails closed. |
| **Observation quote validation (#229 / PR #238)** | Unmatched quote delimiters are rejected even when the trailing words occur in the source conversation; the quote-free retry remains bounded and is revalidated. |
| **RPG handler regression coverage (#230–#232 / PRs #239–#241)** | Added status-selector ownership/stale/duplicate-click tests, Stone Hearth refusal-path tests, and detailed-sheet pet/DEF-cap/other-player-view tests. |
| **Automated opener deduplication (#233 / PR #242)** | Added an explicit punctuation-insensitive regression; signatures compare the first 16 normalized lexical words within the one-hour, channel-aware window. |
| **Core adapter cleanup (#234 / PR #243)** | Removed the unused duplicate `_names()` helper and its now-unused `re` import from `rpg_core_handler.py`. |

## Validation still blocked

- **Live Discord Aethelgard smoke test (#180):** remains open pending an operator-approved run against the deployed bot, a designated test guild/channel, and a disposable character. CI cannot prove live gateway readiness, component delivery, permissions, or deployed recovery.
- **Deployed Linux PDF validation (#206):** automated Linux worker resource-enforcement coverage is merged (#207–#208); production-host kernel, Python build, cgroup/container memory budget, and representative PDF evidence still need to be captured on the deployed host.

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
