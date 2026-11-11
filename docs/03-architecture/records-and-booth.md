# Records and the DJ booth

> Moved out of CLAUDE.md §7 on 6 Nov 2026 to keep that file under its size limit; nothing was
> dropped. CLAUDE.md keeps the rules that are easy to break; this file is the full reference.
> **Read it before changing `utils/audio/records.py`, `beatgrid.py`, `setlist.py`, `library.py`, `mixcheck`, `dj_dashboard.py` or `assets/dj/`.** These files are shared byte for byte with a standalone
> repo (see CLAUDE.md §1), so a change here must keep working without the bot.

**`!music records` mixes the local library** (`utils/audio/library.py`, `records.py`,
`beatgrid.py`). The crate is a `dj_catalog.json` of BPM, Camelot key and genre written *outside* the
repo. The next record is plain Python (key step, tempo within 6% counting half/double time, genre,
nothing recent, a steady opening preferred), levelled to a common LUFS (`gain_db`), and
mixed in NumPy inside the audio source — so §7's "no model, no VRAM" holds. Rules, each learned from
a mix that sounded wrong:

- **Stretch with rubberband, not `atempo`.** `atempo` puts every onset ~20 ms early (measured on
  click tracks); rubberband is within 1 ms. The atempo fallback is compensated (`stretch_latency`).
  A key shift keeps formants and uses the quality pitch path, and both channels are processed together
  (`stretch_filter`): a semitone up without it chipmunked the vocal (Der Kommissar, 24 Oct). Measured on
  a click track, neither moves an onset.
- **The bar is counted, never guessed from accents.** Accents on a log-energy onset curve barely
  differ, and the guess put the incoming bar on beat 2, 3 or 4 — kicks on kicks, claps on the wrong
  beats. Bar one is a record's first strong beat; `grid_at` counts beats from it and keeps the bar
  only when the count comes out whole (`bar_known`).
- **Beats are counted on tracked ticks, not extrapolated.** The onset grid is one line — a bpm and a
  downbeat — and 15–30 s from where it was measured it sat 70–490 ms off the record's real beats:
  half of the October blends put two kicks apart. `tools/maintenance/beat_ticks.py` runs Essentia's
  beat tracker (system Python; the venv has no Essentia) and caches every beat in
  `memory/records/ticks/`; `beatgrid.ensure_ticks` runs it for a record not yet seen, off the voice
  thread. A plan puts the drop on the outgoing's tick and the incoming's bar on its own counted tick
  (`Grid.counted`), and the stretch comes from a least-squares line through all the ticks
  (`Grid.local_beat`) — the tracker's ticks are quantised to its ~11.6 ms hop, and a median of their
  spacings snapped the tempo up to 1% out. The onset grid still decides steadiness and bar one. Do not
  move ticks onto "the kick" by 50–150 Hz energy: an off-beat bassline rises in the same band (one
  record's rise peaked 182 ms before the beat over the record, 43 ms after it in one minute of it).
  Judge a mix the same way: render both decks paired by the mixer's own read counter, not by a second
  beat tracker or that band's energy.
- **A blend takes its time and is staged per band** (`gains`): 64 beats by default; the booth offers
  32 / 64 / 256. The incoming comes in with its highs over one `ramp` and its mids held at `MID_HOLD`
  (−14 dB) while the outgoing plays on whole, vocal and all — the *ride*, both up and locked. On the
  halfway bar the basslines hand over equal-power across `BASS_SWAP_BEATS` (two bars, at most a quarter of the
  blend; one beat was a switch Ekco heard as "way too jerky", 31 Oct) and the mids hand over in `MID_HANDOFF_BEATS` (a bar)
  centred on it, so the
  outgoing's vocal phrase finishes and the incoming's starts on the one; then the outgoing's highs go.
  Until 24 Oct both records' mids sat at 55% through the middle: two vocals stacked, and the outgoing's
  was cut mid-phrase at the swap. A ramp is a quarter of a
  short blend and an eighth of a long one, so EPIC (256) rides for a minute; the ride is the point of
  a long blend, not the bridge to the next record. A blend must leave the incoming `IN_LEFT_S` to play
  alone, and a cue set at the booth is honoured whoever lined the record up. It starts on an 8-bar phrase at the end of a record (4
  for a skip), counted from bar one (`Grid.bar0`), and is fitted before the outgoing's last strong
  beat (`last_strong_beat`), not the end of the file: blending into a fade swaps the bass to nothing.
  Two full records sum through a soft limiter.
- **Two beats play together only when they are measured to lock** (`mixcheck`). The ticks put the bars
  together to within tens of ms — the tracker sits 22 ms early on one record and 38 ms late on another,
  and moves between sections — so a plan is only a proposal. Every planned blend is laid out on the
  played timeline exactly as the mixer will play it and measured bar by bar through the whole overlap on
  each record's kick envelope: locked if most bars agree on one lag inside `LOCK_S`; moved by that lag if
  they agree on a larger one (a 109 ms flam, fixed). The search reaches a quarter beat only, so an
  off-beat bassline can never be chosen as the alignment. The kick envelope is low-band power smoothed
  below the bass's own frequencies (zero-phase) before it is differentiated: per 2 ms hop without that it
  followed each cycle of a 50 Hz kick, and every alignment measured on it was ripple. Three rules, each
  from a measurement:
  - **Only bars where both records have a kick can flam on it** (`NO_KICK`: under 0.4 of the record's own
    kick level is no kick). Hibernation's last 30 bars are pads at a third of its kick level, and the
    judge "measured" lags there out to the ±125 ms edge of its search and refused every pair. But a bar
    with no shared kick still has **claps and hats** (2–5 kHz, `hits_envelope`), and those clashed in 38
    of 58 such bars on real locks: where no kick holds them, the hits must agree (`HITS_CLASH`).
  - **A short overlap must agree in more of its bars** (`needed`: all of 4, 6 of 8). A blend is searched
    for in dozens of places, and a random lag lands inside `AGREE_S` about one time in twelve.
  - **Search before giving up** (`setlist.find_blend`): the planned spot, the incoming cued at another
    phrase (bar 0/8/16/32), the outgoing mixed out up to five 8-bar phrases earlier (a skip: up to three
    4-bar phrases later), then 32 and 16 beats. The planner gives it `SEARCH_S`.
  Check a judge change on click tracks *and* on real pairs in the band you did not measure: a lock is
  only as good as what plays in the bars the judge left out. It cannot always tell a kick from a heavy
  rolling bassline on the beat; that needs ears.
- **Nothing locks: an echo-out, never a bare cut** (`as_echo`, `echo_tail`). Her own pick that locks
  nowhere is swapped for one that does (`RecordsSession._alternatives`: its measured partners, then
  records in stretch of the tempo, those with partners of their own first, `ALTERNATIVE_S`); a record
  loaded at the booth or asked for (`Next.source` "hand"/"request") is never swapped — so anything that
  rebuilds a `Next` uses `dataclasses.replace` (`_cued` rebuilt it field by field, dropped the source,
  and a booth load whose cue had been moved was swapped for her pick). A NEXT or ▶ pressed while a crate
  pick is still being read (`RecordsSession.loading`) waits for it (`after_load`). A NEXT pressed while a
  skip is already planned leaves it alone: each press used to plan it again from now, a phrase later,
  and rerun the search (six presses in nine seconds pushed one echo 8 s on). A booth load or a request
  is searched only from its start or a phrase in (`setlist.HAND_CUES`); scrubbed 32 bars in, Urgent came
  in a minute into the song. What still locks
  nowhere goes out on the bar with its last beat (mids and highs) repeating, `ECHO_FEEDBACK` quieter
  each beat, under the incoming's bar one. On 9 Oct, 40 of 71 planned transitions were cuts — 36 of
  them pairs the graph had never measured (skips and hand loads), which nothing tried to rescue.
- **She picks partners that blend long and stay in a style** (`setlist.transition_rank`). An edge records the
  longest blend that locked: 31% of locking pairs lock only for 16 beats (~7.5 s at 128 bpm: highs, bass swap
  and outgoing inside two bars — a swap, not a blend). The rank keeps long blends first, then prefers a
  higher share of agreeing bars, compatible Camelot keys, the same exact genre (then its broader family),
  artists not already repeated in the run, less pitch correction, and onward partners. The same rank is
  used by set construction, live graph partners and alternative search. Artist variety is soft, never a
  ban. `SET_METHOD` versions the set ranking separately from `METHOD`: a ranking change rebuilds the
  hour-long paths without re-measuring the audio graph. The graph still proves only rhythmic lock; it
  does not yet certify that vocals or midrange content sit well together — see
  [issue #291](https://github.com/Ekco-S64QTN6/Kaiacord/issues/291).
- **She picks partners that lock** (`setlist`). `memory/records/graph.json` holds every tempo-compatible
  pair measured with `find_blend` at the outgoing's end; it is extended, never rebuilt — a new or changed
  record costs its own pairs (a file only retagged keeps them: `library.audio_signature` hashes the
  audio, not the ID3 block). The measuring runs in a niced separate process
  (`tools/maintenance/records_graph.py`, cross-process lock), never in the bot: it is numpy-heavy and in
  the bot's process it held the GIL against the voice thread. A change to how pairs are judged bumps
  `METHOD`, which re-measures everything. When the graph has nothing from the record on air, `_choose`
  measures candidates against its end itself (`_measured_pick`) — the way back into the sets after a
  record with no partners, which is how one cut used to lead to the next.
- **Sets run about an hour** (`make_sets`): depth-first walks through the graph until `SET_TARGET_S` of
  played time (record lengths less each transition's overlap), dropped under `SET_MIN_S`; no song twice
  (`library.same_song`: the title without its version, by an artist they share — "Bad Blood" by two
  artists is two songs); held to one genre family (`FAMILIES`) where the graph allows; whole mixes over
  `MAX_SET_RECORD_S` left out; a record in at most `MAX_USES` sets; starts spread over families and
  tempo bands. Rotated per session (`set_rotation.json`) — the booth's SETS tab lists them, marks the one
  playing and the one the rotation starts next, and ▶ PLAY follows a set from there (`play_set`: its
  first unplayed record is the next pick; a plan not yet begun is called off and the pick in flight
  dropped by generation). `records_graph.py --md FILE` writes the listing.
- **The renderer works from one snapshot per frame.** A skip, a load or a cue from the booth calls a
  plan off on another thread; a frame that read the plan before it and the incoming deck after it raised
  `'NoneType' object has no attribute 'slot'`, and discord.py stopped the set. `read()` takes plan,
  incoming and start frame once, and `_advance` re-checks them under the lock.
- **The bass swap lands on the incoming's bassline** (`beatgrid.bass_entry`: sub-bass per bar from bar
  one, snapped to a 4-bar phrase). Intros hold the bassline back 8–48 bars; when it comes in later than
  the swap's bar, the incoming starts that many bars into its intro, so the swap never hands the low end
  to a kick alone. A cue set at the booth is never moved for it.
- **Key sync** (`library.key_sync`, `music.records_key_sync`): an incoming that clashes with the key
  on air (`Deck.key`, after any earlier sync) and fits a semitone up or down is shifted by rubberband's
  `pitch`, and stays shifted. Rubberband only — atempo cannot move a key.
- **The set's tempo moves** (`music.records_tempo_glide`): 16 bars after a record takes over, it eases
  back toward its own tempo, `GLIDE_STEP` (0.5%) every 8 bars. Not a time-varying stretch: the record
  on air is respliced on a bar onto a fresh decoder at the next ratio (sample-aligned, run in unheard
  for a second, crossfaded over one 20 ms frame), so every `Deck` keeps one constant ratio and plans,
  grids and the booth need no piecewise maths. A glide step never happens while a blend is planned or
  being planned, or a deck is played by hand.
- **Levels are LUFS** (`gain_db`: EBU R128 integrated, to `TARGET_LUFS`). A record is raised only as
  far as its true peak allows (+2 dB into the limiter) and lowered as far as needed — many masters peak
  over 0 dBTP, and capping cuts by peak made the spread worse than mean volume did.
- **Kaia rides the mixer** (`kaia_hands`, `music.records_kaia_hands`, the booth's HANDS): multipliers on
  the automix, locked to bars and scaled by her energy — both records -1.5 dB in a ride (gain staging),
  the hats traded gently every 8 bars in a long ride (never the mids: they carry the vocals), the old
  record's air eased back a little into the swap; alone, a small EQ gesture into the end of a 16-bar
  phrase at most every second phrase (every eighth when calm), let go over the first bar of the next.
  Which gesture is a hash of record and phrase, never random. Until 24 Oct she killed the bass for the
  beat before every swap and gestured into every phrase, snapping back on the one — Ekco: "first five
  minutes with a mixer". Subtle is the rule: a move she makes every time is a habit, not a move.
- **Blend only two steady beats.** Both records' beats tracked (`Grid.tracked`, the Essentia ticks): any
  beat whose ticks run straight is proposed, whatever its onset contrast or bar count — breakbeats included.
  A record not yet ticked falls back to the onset grid: contrast under `BLEND_CONTRAST` (3.5;
  four-on-the-floor measures ≥ 4.2 where it is mixed, rock, breaks and sparse intros 1.8–3.3) or an
  uncounted bar goes out as an echo ("beat not steady enough", most often a fresh hand load). Steadiness
  only proposes a blend; `mixcheck` decides it. The journal's `contrast`/`bar_known` are the onset grid's,
  so a tracked blend there with contrast 1.5 is not a bypass.
- **Check a change on click tracks** through the real `CrossfadeSource` (the incoming first kick must
  land on the planned bar, kicks within a few ms) — a beat detector on real music is not a reliable
  judge of another beat detector.
- **Nothing slow on the voice thread — not even the mix.** `CrossfadeSource.read()` (band filters,
  gain curves, NumPy) runs on a renderer worker; discord.py reads `BufferedRecordsSource`, which only
  dequeues a finished 20 ms frame and returns silence on an empty queue — it never waits for the mixer,
  logs or touches disk (late reads are counted in memory and reported at set end, `[records] set ended`:
  gaps over `LATE_S`, the shorter ones over `JITTER_S`, and the buffer's low-water mark). Opus is told the
  stream is music (`OPUS_SIGNAL`): on "auto" it switched coding mode on quiet bars. A deck whose decoder is behind plays
  silence — on time, so no meter saw it; `DECKS_STARVED` counts those frames (the booth's `starved`, the
  set summary), and a set waits for its first record to have `FIRST_DECK_FRAMES` decoded before playing. The queue is `music.records_audio_buffer_frames` (15 frames ≈ 300 ms, clamped 3–50): every
  booth control and Kaia's hands are heard that much later, so keep it small. The incoming ffmpeg is
  started and buffered by the planner thread. `records-audio-tests.yml` runs `test_records.py` in CI on
  any change to `records.py`.

**The DJ booth** (`dj_dashboard.py`, `assets/dj/index.html`) shows only the mixer's own state —
the decks `CrossfadeSource` holds, their grids, the plan, the band gains applied this frame and the
levels produced — streamed at 20 Hz from 127.0.0.1, with waveforms computed by ffmpeg off the voice
thread. Its controls are real: `records.Controls` (trim, three-band EQ, faders, crossfader, master)
multiplies the automix, and `paused` holds the record on air in place. The free deck works like a
CDJ: a crate click loads it now (`RecordsSession.load` → `CrossfadeSource.load`, which calls off a
blend not yet started and pulls that channel's fader down); dragging its overview, jog or lane moves
its cue (snapped to a bar); ▶ starts it at the on-air tempo with its cue on the same beat of the bar
(`play_hand`); the faders mix, and it takes over after `HANDOVER_S` of the on-air record silent.
NEXT with a deck playing by hand is Kaia finishing the mix (`finish`, a plan of kind `out`). The button has
one name; the line under it (`#skiphint`) says what pressing it does now — five rotating labels did not. PHONES
plays a deck's file in the booth window only (`/audio/<id>`), never on air. Kaia raises a hand-loaded
fader when *her* blend into it starts, not when she plans it — a planned blend is called off by ▶.
A cue set on the record already in her plan (she plans a record's end minutes ahead) calls that plan
off and replans from the cue; it used to be refused, and the jog snapped back to the start. A knob's
pointer is what is *applied* — the hand's setting times the automix and her hands — so her moves turn
it; the hand's own setting is the yellow dot, and a deck not sounding shows the hand's setting. Her own
multipliers are streamed apart from the automix (`hands_now`), and a knob she is holding turns pink — a ring,
an arc from where it would be without her, and a dB badge — or she visibly does nothing (the page has a
`.kaia` grid class; a knob marked with it collapsed the mixer column).
**FX** (header pill, remembered per browser, off under reduced motion) is a stage built only from the stream: a
floor and horizon on the beat of the record on air, level bars from the applied bands, a reticle zooming onto
each knob Kaia's hand is on with sparks the way she turns it, an aura and combo that build through locked blends
(LOCKED on a measured blend, BASS SWAP, PERFECT BLEND when one finishes), ECHO OUT in purple on an echo-out (it
neither adds to the combo nor breaks it), and red — vignette, glitch, shake, combo broken — on a late voice frame.
The floor is one of five scenes (mountains, pyramids, city, ocean, tunnel) travelling toward the horizon at the
beat, picked at load and crossfaded to another on each new record. The mixer's meters are drawn every animation
frame from per-frame levels streamed with the frame counter, mapped to the page's clock (METERS +N ms trims it).
`!music records` and `!music booth` use a booth window already open (`dj_dashboard.viewers`), and the window
stays on its idle screen after `!music stop`.
Nothing in it is decorative state of its own: if the mix did not do it, the screen does not show it. It builds over a set: a heat that eases toward 1 − e^(−combo/5) — the combo being the set's own trailing
run of blends, rebuilt from its history when the page opens — brightens and speeds the floor, lengthens the bars and
sparks, adds embers off the floor on the beat (from a few blends in), a horizon ring and a colour drift (past half);
a clash breaks the combo and the heat falls faster than it rose. **KAIA ON THE DECKS** is her running feed: the
session's `chatter` (`dj_voice`: why the next record — key move, measured bars — the plan and any nudge, an echo-out or a swapped pick
and why, set progress, a hand load), plus the page's timeline lines (blend under way, bass swap, her hands, a
stutter). Templated from real decisions; the music engine still calls no model. The panel itself is Kaia's
codec avatar (the shared engine in `assets/kaia-avatar/`, served at `/kaia/`, see §7 KAIA//RX): the line under her
is the codec subtitle she lip-syncs, the feed and the arousal/energy/valence bars sit behind its LOG toggle, the
readings drive her face (`setOffsets`: valence the smile, arousal eyes and brows, energy the data flow), her
pulse follows the on-air tempo (`setBehavior`), she looks toward the deck a blend brings in, and the FX stage's
PERFECT BLEND and red moments reach her through `window.KaiaBooth.react`. Write-up of the change:
`docs/reports/investigations/2026-10-10-kaia-avatar-rx-and-booth.md` (local, git-ignored). The page draws at 30 fps from
cached canvas sizes (`ResizeObserver`): a `getBoundingClientRect` per canvas per frame after DOM writes forced a
layout each and was over half the booth's CPU.
Knobs drag with pointer capture, never pointer lock (the browser announced "press Esc" on every turn),
and neither page can be zoomed: a pinch cut the mixer in half. No grid column may be widened by its
contents (`min-width: 0`, long labels ellipsised).
Check a change by driving it headless against a real session (Playwright: click, drag, screenshot),
not by reading the HTML.

**Both dashboards open as desktop windows where they can play sound** (`utils/infrastructure/system/app_window.py`): a GTK
window around a WebKitGTK view, run by the *system* Python (it has `gi`; the venv does not), its own
title and window class, no browser around it. Chrome's app mode is the fallback where WebKitGTK is
missing. WebKit's DMA-BUF renderer is off (`WEBKIT_DISABLE_DMABUF_RENDERER`): on this NVIDIA driver
under Wayland it closed the window at once with a protocol error. WebKitGTK plays every sound through a
GStreamer audio sink from `gst-plugins-good`; without it the window opened and played nothing (the
receiver's monitor, the booth's PHONES), so `available()` also requires `autoaudiosink` and a browser is
used otherwise. **On Ekco's machine `gst-plugins-good` is not installed (31 Oct), so both dashboards open in
the browser fallback.** The booth's fallback (`dj_dashboard._browser`) tries Chromium, then Brave, then
Google Chrome: Chrome came first, and a Chrome flatpak with wrappers in `~/.local/bin` was opened in place
of the system Chromium Ekco uses. The monitor plays through Web Audio and falls back to an endless WAV (`/monitor.wav`).
