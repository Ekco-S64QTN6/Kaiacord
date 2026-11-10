# Radio, the scanner and KAIA//RX

> Moved out of CLAUDE.md §7 on 6 Nov 2026 to keep that file under its size limit; nothing was
> dropped. CLAUDE.md keeps the rules that are easy to break; this file is the full reference.
> **Read it before changing anything under `utils/radio/`, `assets/rx/` or `assets/kaia-avatar/`.** These files are shared byte for byte with a standalone
> repo (see CLAUDE.md §1), so a change here must keep working without the bot.

**Radio is a guest on other people's servers.** `utils/radio/` reads eam.watch's and Priyom's
undocumented JSON endpoints. Poll at most every `radio.poll_hours` (default 6 — Ekco's call: it
is a novelty, not a live feed), one request at a time, with the identifying User-Agent in
`utils/radio/fetch.py`, through `public_only_connector`. A response in an unexpected shape raises
`FeedError` and the command says so; it must never become an empty list, which reads as "no
traffic". EAMs and number-station groups are encrypted: nothing Kaia says may claim to decode
one. Research: `docs/reports/investigations/2026-09-24-shortwave-feasibility.md`.

An unsquelched recording that came back in pieces is one broadcast (`watch.stitch`): a KiwiSDR reconnect starts a new file, and one E11 was five posts. Squelched files stay separate, each is a transmission.

A number-station recording is kept only for a keyed tone (`watch.keyed_tone`: prominent within the
recording's own passband, and switching on and off) or speech. Measured against the whole speech
band, CW mode's narrow filter made pure static look tonal, and a steady carrier passed as a tone.

Kaia also **listens** (`utils/radio/watch.py`): scheduled, squelched recordings from public
KiwiSDRs via `kiwirecorder` (fetched into `assets/kiwiclient/` by
`tools/maintenance/fetch_radio_assets.py`, never vendored — no licence file, GPL parts), CPU-only
faster-whisper `large-v3` on band-passed audio, and `phonetic.parse`, which merges the readbacks
and writes `?` where they disagree. Rules: pick receivers with a free slot and no time limit, hold
a slot only while a job or `!radio` needs it, one listen at a time. A scheduled listen is marked
done only when it completed (`watch._run_scheduled`; `run_job` returns `None` for "could not run":
no kiwiclient, no free receiver, every receiver failed) — marked at launch, a busy receiver
directory cost the whole day's slot for that station. **Radio history lives in
`memory/radio/`, never in `knowledge_base/`** — it is noise to retrieval. Accuracy is measured
against eam.watch's human copies (`watch.cross_check`), not claimed. Small and medium Whisper
models, raw audio and the VAD filter all hallucinated on HF audio; don't "optimise" to them
without re-running that comparison.

**The local scanner** (`utils/radio/scanner.py`, `waterfall.py`, `ledger.py`, `dongle.py`) drives an
RTL-SDR attached to the bot. During `radio.local.hours` it hops the voice bands (a pass every ~3 s),
holds on anything standing 10 dB over its own rolling floor (16 dB is taken on first sight), records
it, and classifies it — voice, data, carrier or noise — into `memory/radio/local_ledger.sqlite3`.
`radio.local.nets` pins it to one channel for a net's window. Rules, each from something that broke:

- **Test coverage with the simulated dongle, not by reading the plan.** `test_local_scanner.py` runs
  the real `Watcher` against FM transmissions on a simulated clock. The fixed hop plan it replaced
  caught 2 of 7: slice centres sat on repeater outputs (147.000, 445.000), 80 kHz between slices and
  whole bands were never visited, and a 30 s cooldown ignored every reply. `waterfall.hop_plan`
  tiles each band and moves centres off the seeded and configured channels; keep `COOLDOWN_S` short.
- **The band notebook is regenerated after every watch** (`tools/maintenance/band_notebook.py`, into
  git-ignored `docs/reports/reference/local_band_notebook.md`). It identifies what it can from the
  clips that exist (AFSK tones for packet, a spoken or Morse ID), re-checks voice transcripts against
  today's filter, and keeps the "My notes" section as written. Data bursts keep no clip any more, so
  a data channel first heard now is described by its cadence alone.
- **A transmission stands over its slice, not just over its floor.** Triggers and holds subtract the
  slice's median rise: a household noise source lifted whole slices 10+ dB, and the watch held a
  minute of hiss on frequency after frequency, deaf meanwhile, because the floor adapts only through
  visits and holds block visits.
- **Carrier is measured against a fixed hiss level.** An FM discriminator reads phase, so an empty
  channel demodulates to the same hiss at any input level (`waterfall.HISS_DB`, pinned by a test); a
  frame 6 dB under it has a carrier. A recording's own tail is not a reference: a hold cut off at
  its limit has none. Measure a catch over `carried_audio` — its tail and gaps are hiss, which has
  the digital shape and filed followed voice as data.
- **Voice is followed; hiss is not kept.** After an over that `waterfall.voice_like` passes, `_hold`
  stays on the channel and records each reply into the same catch until `FOLLOW_IDLE_S` of quiet
  (`FOLLOW_MAX_S` at most). `voice_like` wants the voice band swinging under a carrier that quiets
  the hiss 10 dB and holds steady: a weak carrier fading in and out swings too, and was followed for
  five minutes. A reply with no carrier under it ends the follow. A hold that runs the whole minute
  is still followed if it is speech — a linked repeater keeps its transmitter up through a
  conversation. A catch with under 0.1 s of carrier is ledgered as `noise`: not transcribed, not
  clipped, not a channel; a channel configured `mode: digital` is exempt.
- **Packet radio is told by its tones, not its shape.** APRS is Bell 202 AFSK — in-band audio,
  which the digital-shape measure cannot see — so a night's 166 bursts on 144.390 went in as
  carriers and each spent a transcription. `waterfall.is_packet` (the 1200/2200 Hz pair in ≥ 45% of
  ≥ 10 carrier frames; off-air packets 52–62%, hiss 0%, voice at most 36%, a Morse ID too short)
  files them as `data` before Whisper is asked. The band notebook uses the same measure.
- **Only what is worth hearing keeps a clip:** voice, a net, a Morse ID, a reply too short to call voice
  (`scanner.short_reply`: "Yes, sir."; not a sign-off Whisper invents, not the prompt read back), and a
  speech-like carrier Whisper was *not asked* about. Asked and hearing nothing, it is not speech: the 900 MHz
  hoppers and 462.275's telemetry pass `voice_like`, and were kept and highlighted as "sounded like speech".
  A Morse ID (`scanner.morse_id`) is kept once per channel per six hours; 145.690's node sends one every few
  minutes. Clips rotate at 300, so a junk clip pushes out a real one.
- **Speech is transcribed out of its own allowance.** A catch `voice_like` passes spends `SPEECH_PER_NIGHT`
  (400); everything else spends `TRANSCRIBE_PER_NIGHT` (60), which finds a channel's first words. One shared 60
  ran out about 01:30 every night and the rest of the night's dispatch — 50–90 calls — went in as carriers.
  A transcription costs 2–10 s of CPU in int8 (`transcribe.COMPUTE_TYPE`). float32 read dispatch slightly better
  (29 of 37 street names against 27) but held ~6 GB all night — busy dispatch never lets the 15-minute idle unload
  fire — and that RAM matters more than the street names (Ekco, 1 Nov).
- **Dispatch street names are put right against a local street list** (`streets.correct`, via `scanner.fix_streets`;
  ham bands are not touched). The list is a deployment fact: `tools/maintenance/fetch_street_names.py "<area>"
  --write` builds git-ignored `memory/radio/streets.json` from OpenStreetMap; without it nothing changes. A name
  the list lacks, right before its type, becomes the one street of that type it sounds like ("Cockroach Hill
  Road" → Cockrell Hill Road ×8). Rules, each from reading every change over 659 real transcripts: never an
  English word, a direction or a type word ("Avenue" → Avon, "First" → Vista); sound skeleton ≥ 0.8, mean of
  sound and spelling ≥ 0.79; the same syllable count ("Condo" → Coronado, "Levar" → Lear are refused); no
  spacing-only fix; lowercase comma-broken spans left alone. A known tail ("Hill") only blocks a fix of a
  different length. Single-word fixes need nltk's word list; a standalone without it fixes phrases only.
  `ledger_repair.py --streets` applies it to transcripts already logged.
- **A catch is filed where its carrier is** (`waterfall.carrier_freq`): the centroid of the power summed
  while the hold was keyed, not the trigger's smoothed peak rounded to 2.5 kHz, which a voice's deviation moves
  by kilohertz. Nearly every busy channel had a "shadow" row 6.25 kHz up (Dallas dispatch: 354 voice catches on
  460.575, 257 on 460.58125). Measured 31 Oct: 858 key-ups on both UHF spans at 293 Hz all sat within 470 Hz of
  the busier row. Cooldowns stay keyed on the trigger frequency; a tuned channel is filed where it was tuned.
  The dongle reads ~+2 ppm (NOAA 162.400/162.550, 460.575): under a kilohertz, so `radio.local.ppm` can stay 0.
  `tools/maintenance/ledger_repair.py` (dry run unless `--apply`) folds split rows and re-judges kept carrier
  clips after a change to either rule.
- **Listeners hear a transmission, never the sweep.** Nothing is sent while hopping (a tick per hop
  played as pops), and a hold reaches the monitor and a listen-along through `waterfall.Squelch`: open
  only where a carrier ran `OPEN_S` (0.4 s), output delayed by that much so the over is heard from its
  first syllable. Every one of 57 kept voice clips opens it within 4 s.
- **A pulse train is let go.** 463.71875 sends a 0.2 s burst every 1.5 s; each burst reset the hold's
  silence count, so it held the watch the whole minute and was reported as something keying up. A hold
  whose squelch has not opened in `PULSED_DECIDE_S` (4 s) is released and its own channel left alone
  for 5 minutes, doubling on return; channels configured `mode: digital` are exempt.
- **RF without an FM carrier is locked out the same way.** A hold with under `STATIC_CARRIER_S` (0.1 s)
  of carrier — the noise classification's own threshold (`scanner.STATIC_BELOW_S` is it) — got the
  plain 3 s cooldown and came back every pass: 464.9625 750 times in ten nights, the 902–928 MHz hoppers
  2,252 times in a month with no voice or data. It now takes the pulse train's lockout.

**KiwiSDR receivers are judged by what they sent us, not by the directory.** `kiwi.py` keeps
`memory/radio/kiwi_health.json`, fed by every `record`, `smeter` and live stream: digital silence on an
unsquelched recording benches that receiver on that frequency for 14 days (the two best north-eastern
receivers muted 4625 kHz for API clients from Oct 2026 while their S-meter read the buzz); a refusal,
early stop or empty S-meter benches the host for 6 h, doubling; `choose()` skips benched receivers and
ranks one that has worked before 6 dB up. A squelched recording with no openings is a quiet band, not a
mute, and is not judged.
- **A constant carrier is locked out, and the lockout grows.** A full-minute hold that is not speech
  locks ±75 kHz (drifting carriers wandered 55–130 kHz and cost a minute a step) for 30 minutes,
  doubling on each return to 4 h. That reach is a trade-off: roadmap R5d.
- **A wedged read ends the watcher, never the handle.** `rtlsdr_read_sync` cannot be cancelled. If a
  `Stream` reader does not stop within 10 s, `close()` returns False, the dongle is marked so
  `Dongle.close` makes no further C call on it, and the watcher raises `StreamCloseTimeout` and
  exits; process teardown releases the device. Retuning or closing under an in-flight read raced
  native I/O.
- **Each listen-along has its own queue** (`scanner._along_audio`, per guild, bounded, oldest chunk
  dropped when full). One shared queue made two listeners split the stream between them.
- **Every process that holds the dongle dies with the bot.** The bot exits by `os._exit`, which skips
  multiprocessing's cleanup; an orphaned watcher kept the dongle through two restarts. `child_main`
  and `rtl.open_stream` arm `PR_SET_PDEATHSIG`.

- **The watcher runs in a forked child with fds 1 and 2 on /dev/null.** librtlsdr prints its tuner
  chatter from C straight to fd 2, beneath Python's logging, and destroyed the curses dashboard.
  Fork, not spawn: spawn re-imports `Kaiacord.py`, which imports the whole bot.
- **librtlsdr through ctypes, not pyrtlsdr.** pyrtlsdr 0.4/0.5 need `rtlsdr_set_dithering`, which the
  distribution's librtlsdr 2.0.3 does not export.
- **KAIA//RX** (`rx_dashboard.py`, `rx_scope.py`, `assets/rx/`) draws what the watcher measures and
  nothing else: the child sends each slice's spectrum (smoothed over two bins, every 2nd bin, so zooming
  in separates channels; the trigger keeps its 12.5 kHz smoothing) and each pass's lockouts
  on a third queue, `put_nowait` so a missing reader drops frames instead of blocking the sweep, and
  `rx_scope` lays slices into per-band panoramas relative to each slice's median. On one channel (a
  hold, a tune, a net) the child sends every bin, ~25 frames a second, and `rx_scope` keeps that slice
  as the TUNED span (the last of `bands`), which the page switches to: the receiver's own 2.4 MHz, full
  width, a waterfall row per frame. A click tunes the
  running watch in place (see *A tune is a command* below), and a tuned channel is held, recorded and
  classified exactly as the scan would. Only an idle dongle starts a watch for a tune; those starts are one at a
  time (`_restart`; a request mid-restart only marks it to look again, so a burst of clicks ends on the last),
  every watch registers its stop in `_stops` and a restart stops them all, and a stopping watch frees the
  dongle before it finishes its last transcription. ▶ SCAN (`scanner.start_scan`) runs the sweep outside the
  nightly hours for as long as asked and only while a page is open (`DASH_GONE_S`): the page's stream
  calls `seen_by_dashboard`. `!scanner dash` opens it; nothing opens it at night unasked. The top
  row has a fixed height and Kaia's line is clamped: a row sized by its text grew a line and
  squeezed the waterfall every few seconds.
  Each band's panorama is `span / COL_HZ` columns (the ~2.3 kHz the watcher sends while hopping,
  capped at `MAX_COLS`): a fixed 2048 squeezed 20 MHz of 70 cm into ~10 kHz a column and zoomed to
  blocks. **Band waterfalls advance once a pass and only then**; a hold scrolls the TUNED span. A hold
  used to push band rows five times a second, so the band picture lurched between paces, and the page
  flipped between band and span views — it blinked. Each pass also lays every band side by side, low to
  high, into one overview row (`OV_COLS`, max-pooled so a carrier survives): while sweeping, the page's
  dial shows that whole picture with Kaia's needle gliding across it, and on a channel it eases into
  the TUNED span (FOLLOW KAIA; a zoom or drag hands the view to you). Zoomed inside one band it draws
  that band's own panorama. Waterfalls are WebGL2 ring textures (`Falls` in the page), which WebKitGTK
  runs. Kaia herself is the shared codec avatar in `assets/kaia-avatar/` (served at `/kaia/`; the
  same engine as Kaia's and Kaiagotchi's dashboards — keep the copies identical (Kaiagotchi's is
  `kaiagotchi/ui/web/static/js/kaia/`; change the engine in both, byte for byte), put states in the
  page via `KaiaAnimator.registerMood`). Both pages mount her as t2, Ekco's choice for every dashboard
  (10 Nov); `?face=<name>` shows another, and `?face=random` is the shuffled rotation of
  `KaiaCodec.PORTRAITS`, every one once before any repeats, a new shuffle never opening on the last
  (`KaiaCodec.randomPortrait`; `test_kaia_avatar_portraits.py` runs the real file under Node) — and every
  launch (`open_window`, i.e. each `!music records` and `!scanner dash`) bumps `launch` in the page's
  stream; an open page reloads when it changes, because the window is usually reused, not reopened. `tools/maintenance/rx_preview.py` runs the real `Watcher`
  against a simulated sky in real time and serves the page — use it to look at a change, not the bot.
  Write-up: `docs/reports/investigations/2026-10-10-kaia-avatar-rx-and-booth.md` (local, git-ignored).
  `!scanner history` lists voice and data and folds bare carriers into one line; every catch is in
  the page's LOG tab.
  SQL OPEN (`scanner.set_squelch_open`, a shared flag the child reads) plays a tuned channel continuously,
  hiss and all; AUTO plays only what keys up — and a sweep is silent either way, which read as "does
  nothing" on a quiet morning.
  Spectrograms (`spectrogram.py`) are rendered once beside a clip and pruned with it.
- **A tune is a command, never a restart.** The running child takes `{"op": "tune" | "scan" | "gain" | "habits" |
  "marks"}` on its `control` queue (`Watcher._poll`, checked between hops and every read of a hold);
  `scanner.tune_now` / `untune_now` send it from the HTTP thread, and the supervisor in `_watch` sends what nets,
  expiring tunes and the hours ask for. A channel inside the current span only moves the demodulator (`IN_SPAN_HZ`).
  Measured on the dongle: scan→tuned 104 ms, in span 34 ms, another band 180 ms — the restart it replaced waited out
  the hold, refork and reopened the dongle.
- **Listening reads through a `Stream`.** `rtlsdr_read_sync` buffers nothing between calls (and ctypes drops the GIL
  inside it), so processing between inline reads was samples lost: a tuned channel kept 78% of its audio and every
  hold's clip had the same holes. A tuned channel and a hold stream; hopping reads inline after each retune.
- **Demodulate with state.** `Decimator` is overlap-save `resample_poly`: called per chunk it zero-padded every edge
  (a click per read) and slipped on reads not a multiple of 50 samples. Chunked output equals one-shot output.
- **A tuned channel plays through `LiveSquelch`** (open on the second carried frame, no look-ahead): 127 ms from
  key-up to audio, where the scan's `Squelch` holds `OPEN_S` back to keep beacons out of a sweep (613 ms).
- **Habitual data is noted, not held** (`ledger.habitual`, `Watcher._habit_holds`): a channel heard 30+ times in a
  week, never with a voice, brief — 39 of them cost ~28% of the night in holds. Its bursts are ledgered as `seen`
  (no audio; hits and hours still count; never a "catch"); one longer than its usual longest, and every tenth, is
  held. Never a configured channel or a priority bookmark. A rejected peak's skirts are the same signal: skip
  them, or each burst is held 7.5 kHz off.
- **A hold records the rest of its slice** (`_sides`, two at a time): the dongle sees 1.92 MHz while it waits for a
  reply. With the confirm read (`_visit`: a hot bin is re-read at once, not a pass later) and habits, two simulated
  busy nights caught 102 of 179 overs against 88, losing less of each start (median 0.42 / 0.91 s against
  0.69 / 1.18). What still limits it is the follow: up to FOLLOW_IDLE_S on one slice per conversation.
- **Bookmarks are a person's** (`bookmarks.py`, `memory/radio/bookmarks.json`): `priority` lowers the gate there,
  `ignore` removes it — nothing else ignores a channel on anyone's behalf. Gqrx's `bookmarks.csv` imports (yours win)
  and exports. `interest.py` ranks catches (words, new or rare channels, unusual hours, urgent words) and sorts
  channels into talk / data / timer (`ledger.period_of`) / carrier; it labels and orders, it hides nothing.
- **The span streams** (`/span`, binary, a row the moment the watcher makes it): 8192 bins (293 Hz), Blackman-Harris,
  DC removed, 30 rows/s, quantized in the child on `waterfall.DISPLAY_*` (−10…+50 dB). `tools/maintenance/rx_preview.py
  --real` serves the page on the real dongle without the bot — only while the bot's scanner is idle.
- **One dongle.** `rtl.DEVICE` is held by the watch; a live listen sets `rtl.YIELD` and the watch
  gives it up within a hop. A process outside the bot (a hand-run survey) holds the device where
  `rtl.DEVICE` cannot see it, and the bot's watch then fails "busy" and backs off 15 minutes — stop
  any such run before a configured net or the nightly hours. Local repeaters and nets are
  deployment facts and live in config, never in code or tracked docs.
- **Whisper hears the carried audio, with the band's vocabulary.** `_transcribe` hands it `speech_audio`
  (carried runs, padded, 0.3 s apart), not the squelch tail, and an `initial_prompt` by band: dispatch
  words and the APCO alphabet, or ham terms (`prompt_for`). Keep the prompts word lists. Example
  sentences were copied into transcripts ("Westview 38" became "11, rescue 38"; a cross street nobody
  said appeared), and the dispatch list rewrote a ham conversation. Measured on 52 real clips old
  against new and every changed one read. `looks_like_speech` drops repeated filler ("Thank you.
  Thank you") but lets an address read twice through.
- **Transcription on FM static hallucinates.** Auto-detected language on a bare carrier produced a
  Norwegian subtitle credit three times in an hour. The scanner transcribes in English through
  `transcribe.transcribe_speech`, which keeps only segments Whisper scores as speech. Human repeater
  voice has not yet been measured against the 90% bar; NOAA scored 100% on every sentence present in
  the NWS text. The passes live in one place, `scanner.hear` (classify and `ledger_repair.py` both call
  it): strict, then plain for a speech-like catch, then — only if both heard nothing — any language
  without the prompt, counted only at `ANY_LANGUAGE_MIN_WORDS` (6). Forced English returned nothing for
  the Spanish conversations on 462.150/463.825; a short invention ("I don't know." on a 927 MHz hopper)
  stays out.
- **The Quansheng UV-K5** (`tools/maintenance/uvk5.py`) is a handheld, not an SDR: it demodulates one
  channel inside the radio and sends no IQ, so it cannot feed the scanner or KAIA//RX. The tool is
  read-only — find the cable, firmware version, EEPROM backup (calibration at 0x1E00–0x1FFF; take one
  before any flash), bootloader version — and nothing in the bot uses it. A K-plug programming cable
  carries no audio; listening needs an audio path (an AIOC, or a 3.5 mm cable into a USB sound card).
  **Kaia never transmits** — Ekco's decision; any PTT line an audio interface offers stays unused.
- **discord.py needs a real file for FFmpeg's stderr.** `subprocess.DEVNULL` is an int; it fails
  `.fileno()` and gets piped through a thread that crashes on `.write()` every play.
