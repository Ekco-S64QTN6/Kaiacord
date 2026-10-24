# Roadmap

What is open, and the call on each. Updated 24 October 2026.

Each item carries a decision: **Yes** (to build), **Watch** (measure before building), **Owner's
call**, or **No** (researched and declined, with the reason). Closed work is in `git log` and the
pull requests.

## To build

| Item | What | Effort | Call |
|:--|:--|:--|:--|
| **Kaia knows her own commands** | Asked about `!help`, she described it as an internal diagnostic tool. When a turn asks about her commands, inject the registry's command list (names and one-line summaries). | 1–2 h | Yes |
| **Stitch fragmented shortwave broadcasts** | A KiwiSDR reconnect splits one number-station broadcast into fragments, each posted. Join an unsquelched listen's WAVs before processing, one post per scheduled broadcast. | ½ day | Yes |
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
| **Split the rest of `_dungeon_combat_round`** | Rewards and loot are split out and tested (#45). Context loading and the victory / defeat / continue branches are still one function. | Yes, when next touched |
| **Split `rpg_core_handler.py`** | 2,675 lines; navigation and world handlers would separate cleanly. | Yes, when next touched |
| **Dead `bone_shield_passive`** | Read in `combat_engine.py` and `rpg_core_handler.py`; no class defines it. | Yes, 15 min |
| **More Spine creatures** | 186 distinct monsters across 77 floors, 5–7 per floor. More rare spawns per zone would add variety. | Content, optional |
| **Shadowblade endgame damage** | The highest sustained damage per round (crit on 17 with the Voidstep Blade), offset by the Rogue's low HP. | Watch |
| **Board games as real game state** | Tic-tac-toe with Python holding the board, about 2 h. | No — one game asked for in five months |

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
