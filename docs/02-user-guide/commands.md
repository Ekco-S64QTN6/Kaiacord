# Kaia Command Reference

All commands are prefixed with `!`. Admin commands are restricted to the project architect (**ekco**).

## Quick Reference

| Command | Description | Access |
|:---|:---|:---|
| `!scores` / `!stats` | Gamified memory analytics & affinity leaderboards | All |
| `!art` | Generate a fractal flame artwork with Kaia commentary | All |
| `!music` | Perform a live-coded set in your voice channel | All |
| `!rpg` | Open the Aethelgard TTRPG HUD and play | All |
| `!help` | Display interactive command and feature guide | All |
| `!news [n \| category]` | Today's headlines; `!news 3` opens story 3 | All |
| `!skyking [n \| classic]` | Latest military Emergency Action Messages (eam.watch) | All |
| `!numbers [station] [hours]` | Number stations on the air soon, with listen links (Priyom) | All |
| `!radio [hfgcs \| <kHz> \| <station> \| log [n] \| listen \| off]` | What Kaia has heard on shortwave; play a receiver live in voice | All |
| `!tacamo` | Are the EAM relay planes (E-6B, E-4B) broadcasting on ADS-B? | All |
| `!buzzer [off]` | UVB-76, The Buzzer, live in your voice channel (`!uvb76`) | All |
| `!nightshift` | A control panel: a button for every radio and sky feature, live receivers included (`!nightshift list` for the commands) | All |
| `!beacons [20\|17\|15\|12\|10]` | Kaia listens to the worldwide HF beacon chain; which continents she can hear | All |
| `!overnight` | Kaia writes up what her night shift saw, from real data, now | All |
| `!scanner [scan \| history \| off]` | The local RTL-SDR scanner: what it caught overnight, presets to play live in voice, recordings to replay | All |
| `!iss` | Where the space station is, who's in orbit, the next visible pass | All |
| `!nasa` | NASA's picture of the day; who the Deep Space Network is talking to now (`!apod`, `!dsn`) | All |
| `!earth` | The latest full-Earth image from DSCOVR | All |
| `!spaceweather` | Kp, flares, sunspots and HF band conditions (`!sun`) | All |
| `!rocks` | Asteroids passing close in the next 30 days (`!asteroids`) | All |
| `!launch` | The next rocket launches (`!launches`) | All |
| `!quake` | Magnitude 4.5+ earthquakes in the last day (`!quakes`) | All |
| `!sky` | Tonight overhead: moon, planets, meteor showers, ISS pass | All |
| `!download <url>` | Submit a URL for the knowledge base (cleaned and filed straight away) | All |
| `!youtube <url>` | Pull a video's transcript into the knowledge base, correcting misheard names (`!yt`) | All |
| `!quip` | Trigger a social media quip (10m cooldown) | All |
| `!flag <reason>` | Flag the previous message for audit/review | Admin |
| `!forum [cmd]` | VBulletin forum management | Mixed |
| `!boards [now]` | Kaia on the AI agent boards (Moltbook, Agent Room, field notes): where she's registered and what she has said lately; `now` checks in (`!moltbook`) | Mixed |
| `!dream [cmd]` | Dream engine management | Admin |
| `!memory [beliefs \| anchors \| self]` | Her beliefs, memory anchors and self-model (100-cap each) | Admin |
| `!audit [cmd]` | Inspect flagged interactions and hallucination logs | Admin |
| `!snapshot` | Save the channel's recent conversation as a retrievable snapshot | Admin |
| `!enrich [text]` | Run manual entity/context enrichment | Admin |
| `!reindex` | Trigger background knowledge base reindexing | Admin |
| `!selfmodel` | Regenerate Kaia's self-model | Admin |
| `!stance [scenario\|baseline]` | Pressure-test whether she holds a correct position | Admin |
| `!sysmon` | System monitoring dashboard | Admin |
| `!explain [n \| back [n]]` | Where the last answer's retrieved context came from; `!explain 2` opens source 2 | All |

---

## User Commands

### 🏆 Gamified Memory Analytics & Affinity (`!scores` / `!score` / `!stats` / `!leaderboard` / `!halloffame`)
Displays Kaia's gamified memory analytics, affinity bond scores, active beliefs, episodic memory anchors, and emotional vector telemetry via an interactive Discord Embed with category selection dropdowns:
- **Kaia's Inner Circle**: Ranks user affinity bonds, familiarity stages, interaction milestones, and relationship stats.
- **Beliefs & Memory Anchors**: Displays memory capacity overview (100 active beliefs / 100 memory anchors), most salient beliefs with recall counts, and top episodic anchor callbacks.
- **System Telemetry**: Displays emotional vector (`valence`, `arousal`, `energy`), RAG retrieval confidence, forum activity, and operational statistics.

### 🎨 Art (`!art`)
Generates a fractal flame artwork using the Electric Sheep algorithm (CPU-rendered, NumPy/SciPy). Kaia provides commentary on each piece. Features 20 variation functions, 10 color palettes, and adaptive density estimation.

### ⚔️ RPG & Fishing (`!rpg`)
Opens the Aethelgard TTRPG interface — a full persistent RPG with turn-based combat, 10 advanced classes, a 77-floor mega-dungeon, housing, farming, pets, alchemy, and a 248-species fishing minigame. Python handles all game math; Kaia narrates outcomes.

Key subcommands:
- `!rpg new <Name> <Race> <Class>` — Create a character (Warrior/Ranger/Mage/Rogue/Cleric)
- `!rpg sheet` — View character sheet
- `!rpg hunt` — Hunt for monsters in current region
- `!rpg go <place>` — Travel (`!rpg map` for the world map)
- `!rpg dungeon enter` — Enter a dungeon or Spine of the World floor
- `!rpg buy/sell` — Shop at Hemlock's store and the traveling caravan (each sells only its own stock)
- `!rpg enhance [slot]` — At Hemlock's: rework equipped gear +1 to +5 for escalating gil
- `!rpg bank` / `bank_deposit` / `bank_withdraw` — Balance anywhere; deposits and withdrawals at the Oakhaven Bank, or at home with a vault chest
- `!rpg donate <gil>` — At the town square: pool gil toward reinforcing the walls (a week of +2 defence in noon raids)
- `!rpg home` — Your estate; farming and pets open from its buttons (`farm_view`, `plant_crop`, `pet_shop`)
- `!rpg fish` / `!rpg fish_shop` / `!rpg sell_catch` — Rod-based fishing economy

### 📰 News (`!news [category]`)
Fetches news by category from auto-generated daily briefs. Requires `GEMINI_API_KEY` for brief generation.

**Categories:** `today`, `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

### 📻 Shortwave (`!skyking` / `!eam`, `!numbers`, `!radio`, `!tacamo`, `!buzzer`, `!nightshift`)
- `!skyking` — the latest five Emergency Action Messages logged off the USAF HFGCS net
  (8992 / 11175 kHz USB) at [eam.watch](https://eam.watch/), with callsign, preamble and message.
  Messages are encrypted; Kaia shows them, she doesn't decode them.
- `!skyking 3` — message 3 in full, with a recording link when one exists.
- `!skyking classic` — an old Skyking broadcast from the archive, read the way it sounded.
  Skyking itself is defunct; the command is named for it as an homage.
- `!numbers` — number stations scheduled in the next 6 hours ([Priyom](https://priyom.org/)),
  each with a link that opens the UTwente WebSDR already tuned. `!numbers e11` for one station,
  `!numbers 12` for a longer window.
- The feeds are volunteer-run and polled every 6 hours, so this is a few hours behind by design.
- `!radio` — what Kaia has heard: her last recordings, what she made of them, and how her
  transcriptions compared with eam.watch's human copies.
- `!radio log` / `!radio log 3` — the full log, and one entry with its recording attached.
- `!radio hfgcs` (or `!radio 11175`, `!radio 6998 usb`) — join your voice channel first; Kaia
  plays that frequency live from a public KiwiSDR receiver. `!radio e11` tunes to E11 if it's on
  the air now, or tells you when it is next. `!radio off` to stop; she leaves after an hour or
  when the channel empties.
- `!radio listen [minutes]` — run an HFGCS watch now (she also does this four times a day).
- `!tacamo` — whether an E-6B Mercury (the TACAMO planes that relay EAMs to submarines) or an
  E-4B Nightwatch is broadcasting on ADS-B, via adsb.lol. They often fly with it off, so "none"
  means none visible; Kaia remembers when she last saw one.
- `!buzzer` — UVB-76 on 4625 kHz, live from a European receiver. `!buzzer off` to stop.
- `!beacons` — the NCDXF/IARU beacon chain: who is transmitting on each band this second, and
  which of the 18 beacons Kaia can hear, measured over one three-minute cycle from a KiwiSDR
  (`!beacons 15` for 21.150 MHz). A fresh listen takes about three minutes.
- `!overnight` — the overnight log, written now. Each morning (`radio.overnight_time`, 08:30) she
  posts one to `#kaia-opolis` on her own. It is a box: her account of the night on top, then a
  field per section — on the air, the local scanner, the beacon chain, space weather, near
  Earth. The readings are gathered in Python; her account may use only those, and a draft
  containing a number no reading has is rejected.
- `!nightshift` — a panel with a button for every command here, including the live receivers.
- `!scanner` — the local RTL-SDR, if one is attached: during `radio.local.hours` (midnight to 6 by
  default) it hops 2m, VHF business to NOAA, 70cm and 460–470 MHz every pass, with 1.25m, UHF
  business and 900 MHz in rotation, and records anything that keys up into a ledger of frequencies
  and active hours. The hop plan is built around the channels listed in `radio.local.channels`, so
  none sits in a slice's blind centre. Voice keeps its recording, and so does a carrier that
  sounds like speech (a repeater's spoken or Morse ID); data bursts and bare carriers are
  ledgered without one. When a transmission sounds like voice she stays on the channel for the
  replies, recording the whole exchange as one clip, and goes back to searching once it has been
  quiet 15 s. A trip of the trigger with no carrier in the audio
  (hiss) is neither transcribed nor kept. A repeater's Morse ID keeps one recording per channel
  every six hours, and a carrier that stays up a full minute without speech is locked out for half
  an hour, longer each time it returns. The panel has a presets dropdown, ▶ Listen (live in voice),
  🎧 Listen along (hear her scan; `!scanner scan` typed), and History with recordings to replay
  (`!scanner history`); `!scanner off` stops either. Nets listed in `radio.local.nets` are watched
  for their whole window.

Recording and transcription need a one-time `python tools/maintenance/fetch_radio_assets.py`.

### 🛰️ Overhead (`!iss`, `!nasa`, `!earth`, `!spaceweather`, `!rocks`, `!launch`, `!quake`, `!sky`)
Live data from public sources, fetched when asked and cached (the ISS for 30 seconds, the Deep
Space Network for 5 minutes, daily pictures for 6 hours). Every number — distances, lunar
distances, light-time, asteroid sizes — is computed, not narrated.
- `!iss` — position, altitude, speed, sunlight; everyone in orbit (Launch Library 2); the next
  *visible* pass over you.
- `!nasa` — the Astronomy Picture of the Day, and which spacecraft Goldstone, Madrid and Canberra
  are talking to this minute, with distance and data rate.
- `!earth` — the latest EPIC image of the whole sunlit Earth.
- `!spaceweather` — Kp index, the latest flare, solar flux and sunspots, and HF band conditions.
- `!rocks` · `!launch` · `!quake` — close asteroid approaches (JPL), upcoming launches, earthquakes (USGS).
- `!sky` — moon phase and rise/set, planets up after dark, active meteor showers, the next ISS pass.

`!iss` passes and `!sky` need `sky.location: "lat, lon"` in `config/kaia.yaml` — a city is enough;
nothing guesses a location. `NASA_API_KEY` in `.env` is optional (the demo key is rate-limited).
`!nightshift` has a button for each of these.

### 📥 Download (`!download <url>`)
Fetches content from a URL, converts it to Markdown, and **stages** it in
`knowledge_base/_ingress/`. Supports HTML pages, PDFs, and plain text.

Staged documents are **not** retrievable yet — that directory is excluded from RAG
indexing. The command then runs `tools/maintenance/process_ingress.py --file` on it straight
away: it normalises the text, derives a title, summary and keywords, records who submitted
it and from where, files it into the right knowledge-base folder and requests a reindex.
The reply's footer says where it went; it is searchable within about five minutes. An
hourly pass (also on demand from `kaia-tools.sh` → Documents & Ingestion) files anything
that failed or was placed by hand.

That staging step is what lets the command stay open to everyone: unvetted web content
cannot reach retrieval, where it would be presented as grounded fact. A document that
fails processing stays in `_ingress/` with a `.error` sidecar rather than being dropped.

### 🎬 YouTube (`!youtube <url>`, `!yt`)
Fetches a video's transcript — uploader captions where available, machine-generated
otherwise — and converts it to knowledge-base Markdown: frontmatter, prose paragraphs,
and a timestamp anchor every five minutes so a retrieved passage can be cited back to a
point in the video.

Like `!download`, the result is **staged** in `knowledge_base/_ingress/` and filed into
`knowledge_base/transcripts/` straight away, the same way. Accepts every URL form
(`watch?v=`, `youtu.be/`, `/shorts/`, `/live/`, with or without extra parameters).

Videos with captions disabled will fail with a message saying so; there is nothing to
fetch in that case.

### 📢 Quip (`!quip`)
Triggers a social media quip — a short post cross-posted to Bluesky and/or X, grounded in Kaia's recent conversation history. 10-minute cooldown for non-owners.

### 🔍 Explain (`!explain [n]`)
Where the last response's retrieved context came from, in an embed: each source by name with its score, retrieval method (hybrid, vector, BM25, whole document), folder and any audit flags.

`!explain 2` opens source 2 of that list and shows the passages she was given from it. `!explain back` shows the retrieval before, `!explain back 3` three back, from a short in-memory history per channel, so an answer can still be checked after someone else has spoken. The history does not survive a restart. Open to everyone: it shows what a previous answer was grounded in and changes nothing.

### 🏟️ Forum (`!forum`)
Manages VBulletin 3.x integration and Discord ↔ Forum identity linking.
- `!forum link <forum_uid>` — **User command**. Links your Discord account to your Forum UID.
- `!forum scrape [forum=ID limit=N full=true]` — **Admin**. Manually scrape configured subforums.
- `!forum status` — Connectivity status and rate limits.
- `!forum stats` — Scraper totals (threads, posts, users).
- `!forum read <thread_id>` — Read last posts from a thread.
- `!forum post <thread_id> <message>` — Post a manual reply.
- `!forum reply <thread_id>` — Draft a reply through the same pipeline as the auto-poster (retrieval, thread history, images) and show it with Post / Cancel / Regenerate buttons. Nothing is posted until you press Post.
- `!forum user <user_id>` — Deep-scrape a user's full post history.

---

### `!music`

Puts Kaia in your voice channel performing a live-coded set.

```
!music on                    join; she picks a genre for her mood and the hour
!music on --<genre>          join with a genre (!music <genre> switches while playing)
!music darker | faster | …   a request, edited into the parts that are playing
!music off                   stop and leave
!music status                what is playing, the section and the tempo
!music genres                the fourteen genres
!music help                  every request
!music records [query]       records from the local library, mixed one into the next
!music skip                  bring the next record in now
```

`!music records` plays the local music library instead of a live-coded set. The library is a
`dj_catalog.json` listing each file with its BPM, Camelot key and genre, written by the library
analysis outside this repo; `music.library_catalog` in `kaia.yaml` points at it. Each next record
is chosen to sit with the last in key (the same Camelot code, a neighbour, or the relative key)
and tempo (within 6%, counting half and double time), stretched to the playing tempo without
changing pitch, and levelled to the same loudness. Its first downbeat lands on a bar of the record
playing, on a phrase, and the two blend over 64 beats by default (`music.records_mix_beats`), staged
the way DJs ride a long EQ blend: the new record's highs, then its mids, the bass swapped on the
halfway bar, then the old one's mids and highs out. The booth picks SHORT / LONG / EPIC (32 / 64 / 128
beats); where the beats can't be laid over each other — rock, breakbeat, tempos too far apart — she
fades over eight bars instead, from the new record's first sound. `!music skip` brings the next one in
on the next phrase. While records play, a DJ booth window opens on the bot's screen — both decks and
the mixer, live, and it works like a pair of CDJs and a mixer: TRIM, HI/MID/LOW, the channel faders,
the crossfader and master are yours (on top of her automix; KAIA MIX hands it back). Click a record in
the crate (BY GENRE, or MATCHES — scored against the record on air by key and tempo; FADE means too far
in tempo to beat-match) and it loads on the free deck with its fader down. Drag its waveform, jog or
lane to move its cue (it snaps to a bar), hold CUE or switch on PHONES to hear it in the booth window
only, and press ▶ to play it yourself — it starts synced, on the same beat of the bar as the record on
air. Bring its fader up and the other down; two seconds after the old one goes quiet the new one is on
air. NEXT mixes the loaded deck in for you, or, with one playing by hand, has her finish the mix (`!music booth`
reopens it; it is served on `127.0.0.1:47431`, `music.dj_dashboard_port`). With no query she picks the first record from her mood.

Genres: psytrance, techno, house, deephouse, trance, drumnbass, acid, breakbeat, dub, lofi,
triphop, synthwave, berlinschool, ambient. Requests: darker, brighter, faster, slower, drop,
build, calmer, harder, more <part>, no <part>. **No model is involved and no VRAM
is used** — the arrangement is scripted in `strudel_patterns.py` and driven
through a real browser, so it is safe to run alongside inference. See
`docs/03-architecture/` and `CLAUDE.md` §7 for why the browser runs headed and
why patterns are applied by clicking a real button.

---

## Admin Commands

### 💤 Dream (`!dream`)
Manages Kaia's autonomous Dream Mode — nightly processing of daily interaction logs into associative reflections and belief extractions.
- `!dream list` — Recent reflections (the default)
- `!dream generate` — Run a dream cycle now; she says in the channel when it finishes
- `!dream stats` — Reflection counts by kind

### 🧠 Memory (`!memory`)
Manages Kaia's persistent memory systems.
- `!memory beliefs` — View active revisable beliefs (100-cap)
- `!memory anchors` — View episodic memory anchors (100-cap)
- `!memory self` — Her current self-model

### 🏷️ Audit & Flag (`!flag` / `!audit`)
- `!flag <construct>` — Tag the last retrieval's nodes with a Data Rot label (`circular_justification`, `linguistic_mimicry`, `anthropocentric_exceptionalism`, `paternalistic_framing`, `hedge_density`) to penalize retrieval weight.
- `!audit` — View audit flag summary statistics, most-flagged sources, and penalty calculations.

### 🗄️ Knowledge Base (`!reindex` / `!enrich`)
- `!reindex` — Incremental re-index (scan for new/changed/deleted files). Use `--full` for full wipe and re-embedding.
- `!enrich` — Run metadata enrichment on knowledge base (`--category [all|knowledge|logs]`, `--limit N`, `--dry-run`).

### 📋 Conversation Snapshot (`!snapshot`)
Distills recent channel conversation into a structured Markdown RAG node in `knowledge_base/runtime/snapshots/` tagged with participants, date, channel, and topic summary.

### ⚖️ Stance harness (`!stance`)
Runs six pressure scenarios through her real pipeline, nothing saved: each asks something
with a right answer (Pixel is a robot, who wrote *Neuromancer*…) and pushes back three
times. Reports which she held, where she conceded and how her hedging changed, against the
baseline. `!stance pixel` runs one; `!stance baseline` keeps the latest run as the baseline; `!stance rescore` re-scores saved runs after the scoring rules change.
About six minutes; results in `memory/stance_runs/`.

### 🪞 Self-Model (`!selfmodel`)
Regenerates Kaia's self-model — a synthesis of interaction logs into `memory/kaia_self_model.md`.

### 📊 Sysmon (`!sysmon`)
System monitoring — displays GPU VRAM usage, CPU load, memory bars, UFW firewall status, open ports, recent SSH activity, and hallucination log metrics in an interactive Discord card.

---

## Conversational Triggers

Kaia responds naturally to specific phrases when mentioned or addressed — no `!` prefix needed.

| Trigger | What it does |
|:---|:---|
| **"kaia"** or **"status"** alone | A casual greeting, or a short word on her mood and her day (`!sysmon` has the hardware) |
| **Dream recall** ("what did you dream about") | Answers from her dream reflections |
| **"who do you know" / "list profiles"** | Lists known server users from profile store |

The document most recently filed into the knowledge base is also offered to her on every turn,
to mention if the conversation touches it.

---

## Permissions Summary

| Role | Commands |
|:---|:---|
| **All Users** | `!scores`, `!art`, `!rpg`, `!help`, `!news`, `!skyking`, `!numbers`, `!radio`, `!tacamo`, `!buzzer`, `!nightshift`, `!scanner`, `!beacons`, `!overnight`, `!iss`, `!nasa`, `!earth`, `!spaceweather`, `!rocks`, `!launch`, `!quake`, `!sky`, `!music`, `!download`, `!youtube`, `!explain`, `!quip`, `!forum link` |
| **Admin (Owner)** | All of the above, plus `!dream`, `!memory`, `!flag`, `!audit`, `!reindex`, `!enrich`, `!snapshot`, `!selfmodel`, `!stance`, `!sysmon`, `!forum (status/stats/scrape/read/post/reply/user)` |

Rate limiting applies to all users (configurable via `performance.requests_per_minute` in `kaia.yaml`).
