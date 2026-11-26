# Records and the DJ booth

> Moved out of CLAUDE.md §7 on 6 Nov 2026 to keep that file under its size limit; nothing was
> dropped. CLAUDE.md keeps the rules that are easy to break; this file is the full reference.
> **Read it before changing `utils/audio/records.py`, `beatgrid.py`, `setlist.py`, `library.py`, `mixcheck`, `dj_dashboard.py` or `assets/dj/`.** These files are shared byte for byte with a standalone
> repo (see CLAUDE.md §1), so a change here must keep working without the bot.

## Product goal: an expert DJ, not a mechanically tidy crossfade

> A technically perfect transition isn't necessarily a great DJ transition. Beat grids can align
> perfectly while the musical result is boring, overcrowded or emotionally wrong.

This is the owner-confirmed north star for `!music records`: Kaia should be able to build an
hour-long set in which a listener hears an unexpected but coherent transition, a beautifully timed
breakdown, a clever vocal overlay or a perfectly landed effect and thinks, *that was bloody good
mixing*. The goal is musical storytelling and taste — not a sequence of green lock indicators.
This is a product requirement, not a claim that the current implementation already meets it.
Tracking: [#402 — Kaia's musical judgment and DJ skills](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402),
[#403 — professional booth controls](https://github.com/Ekco-S64QTN6/Kaiacord/issues/403), and
[#401 — independent DJ dashboard test selection](https://github.com/Ekco-S64QTN6/Kaiacord/issues/401).

The implementation is split into reviewable layers: [#408 — audio-cache identity correctness](https://github.com/Ekco-S64QTN6/Kaiacord/issues/408),
[#404 — cached musical-state profiles](https://github.com/Ekco-S64QTN6/Kaiacord/issues/404),
[#405 — set-level musical planning](https://github.com/Ekco-S64QTN6/Kaiacord/issues/405),
[#403 — real booth/mixer capabilities](https://github.com/Ekco-S64QTN6/Kaiacord/issues/403),
[#406 — composable skill/action execution](https://github.com/Ekco-S64QTN6/Kaiacord/issues/406), and
[#407 — records-mode listener requests](https://github.com/Ekco-S64QTN6/Kaiacord/issues/407).
The order and dependencies are maintained in the roadmap.

### The quality hierarchy

**Technical correctness is a gate and a safety constraint, never the artistic score.** Beat-grid,
phase, key, tempo and phrase alignment tell Kaia what can be executed safely. They do not tell her
whether a transition is interesting, emotionally right, spacious, or too crowded. A pair that locks
perfectly can still be the wrong choice. A less obvious partner, a deliberate wait, a phrase cut, a
breakdown handoff or a controlled contrast can be better than the safest long blend.

Every decision should account for the musical roles and structures in both records: vocals and
hooks, lead lines, bass movement, drums and percussion, breakdowns, intros/outros, density, energy,
tension, release and the space between events. Ask what the outgoing record is saying at this
moment, what the incoming record adds, whether the overlap makes a new musical idea or merely
stacks competing material, and whether the listener needs a build, a breath, a surprise, a release
or a change of direction. A longer blend, a louder drop, more layers, higher energy or more effects
is not automatically better.

Plan the **whole set**, not just the next pair. An hour should have pacing, contrast, coherent
progression, energy contour, tension/release, callbacks, surprise and room to breathe. It should
not be forced through one fixed energy curve or one genre formula; the records and the moment
should determine the story. Kaia must be able to reject a technically valid blend or wait for a
better moment, and to take a musically justified risk when she can execute it with control.

### The DJ's toolbox

The target is a composable skill library. Each skill needs a musical purpose, preconditions,
phrase/timing rules, bounded parameters, an explanation of why it is being used, and a safe exit
or recovery path. The repertoire should cover:

- **Deck and rhythm craft:** beatmatching, phase nudges, live pitch bend and pitch/tempo rides;
  cue, hot-cue and memory-cue work; phrase cuts; beat juggling; loops of useful phrase lengths,
  loop rolls and slip-style rolls; cue juggling; and genuine scratch vocabulary (baby scratches,
  chirps, transforms and flares).
- **Transition craft:** short and long blends, clean cuts, drop swaps and double drops,
  breakdown handoffs, intro/outro layering, bass and vocal/presence handoffs, call-and-response,
  acapella/instrumental overlays and coherent mashups; genre-aware phrasing for house, progressive,
  trance, techno, breaks, electro and related styles.
- **Effects and performance:** high/low-pass filtering, echo, delay, reverb, phaser, flanger,
  gated/stutter cuts, beat repeats, pitch drops, risers/noise, sampler or one-shot drops,
  backspin/rewind and controlled brake/spin-down effects.

This list is a capability target, not permission to fake controls. A scratch must be generated by
real scratch/cue manipulation, not by seeking the full track playhead and calling it a scratch.
An FX control must alter the audible signal through a real, bounded effect path. A loop, roll,
overlay, sampler or cue action must have actual engine support before Kaia can claim to perform it.
Tricks exist to serve the music; random effect spam is bad DJing.

### Decision and evaluation loop

1. **Listen and understand** both records and the live set context using real preview where
   available plus cached/background audio analysis.
2. **Form an intention** for the next musical moment and the wider set arc.
3. **Choose deliberately** whether to blend, wait, cut, layer, contrast, tease, loop, overlay or
   use an effect — and record the musical reason, not only the technical score.
4. **Execute precisely** with phrase, phase, level, EQ, timing and effect control suited to that
   intention.
5. **Evaluate the audible result**, including clashes, clutter, vocal interference, loss of impact,
   missed phrasing and whether the moment achieved its purpose.
6. **Adapt** the next move and the larger set plan from what was heard.

Unit tests and technical metrics remain essential for synchronization, safety, bounds and
reliability, but they cannot prove taste. Acceptance also requires listening to real local-crate
sets and independent/blind human assessment of musicality. Record examples where Kaia rejects a
technically valid blend, deliberately waits, chooses a surprising partner, times a breakdown or
uses an effect for a clear reason. Do not call the target complete on unit tests alone.

### Current implementation versus target

The current records engine already has two decks, tracked beat grids, tempo stretch and key sync,
phrase-aware transition planning, measured kick/hit lock checks, band-split EQ and bass/presence
handoffs, cached `songmap` curves, a setlist graph, and a limited phrase-locked `kaia_hands`
gesture set. These are valuable foundations, not expert musical judgment.

The current chooser still leans on pre-measured compatibility, key/tempo, genre/family, blend
length and technical lock results. `mixcheck` answers a narrow synchronization/clash question; it
does not grade musical taste or the emotional result. `songmap` finds structural proxies, not
reliable vocal stems or a complete understanding of a record's arrangement. The current hands
choose from a small set of predetermined gestures; the existing booth is not yet full professional
CDJ/mixer parity. Richer musical reasoning, the composable skill library, a full set-level arc,
and audible evidence that the choices are good are still work to build.

**Cache identity is a prerequisite for musical intelligence.** The current path/mtime-based caches
can reuse previous audio analysis or transition evidence when media is replaced at the same path.
This affects song maps, kick/hit envelopes and levels, loudness/true-peak gain compensation,
measured transition edges, beat-tick JSON, path-keyed beatgrid calculations and booth waveforms. The shared `audio_signature()` now streams a complete BLAKE2 digest of the audio payload,
excluding leading ID3v2 and trailing ID3v1 metadata. It caches that digest against device/inode,
size, mtime and ctime so ordinary same-path, same-size replacements with a preserved mtime
invalidate immediately; a full revalidation is forced at least every five minutes to cover
unusual filesystems. Every map, envelope/level, beat-tick, beatgrid, loudness, graph and booth
waveform cache must validate this identity and invalidate related in-memory/disk results together.
Background analyses recheck identity before publishing their result. This is [#408](https://github.com/Ekco-S64QTN6/Kaiacord/issues/408),
a prerequisite for [#404](https://github.com/Ekco-S64QTN6/Kaiacord/issues/404). Full hashing and
refresh must stay off the 20 ms voice callback.

### Phrase-level musical-state profiles (#404)

`utils/audio/songmap.py` extends the existing normalized STFT map; it does not build a
second analyser. Version 3 maps contain:

- `full`: all-frequency mid-channel energy relative to the record's usual level.
- `bass`: energy below 180 Hz, relative to the record's usual level.
- `lead`: sustained 300–3400 Hz centre energy after hit suppression. It is a lead/midrange
  proxy, **not** vocal detection or stem separation.
- `upper`: 3500–5200 Hz energy at the analyser's 11.025 kHz sample rate. It is an upper-band
  proxy, not a full-spectrum air detector.
- `transient`: positive spectral flux, useful as an activity/change proxy but not a drum
  classifier or onset-truth label.

`phrase_profile(path, bpm)` retrieves the identity-keyed cached map and beatgrid on a
background worker, then rechecks the source identity before combining them. Where a counted
bar one is known, windows align to the requested phrase length (four bars by default); a
pre-beat intro remains a separate unaligned window. If the grid cannot count bar one, the
API returns fixed-time windows with `aligned=False` and `bars=None`, while retaining
any raw tracker BPM/contrast as uncalibrated metadata. Raw `start`/`end` seconds are
always retained.

Each window exposes normalized feature levels, local full-energy change, and optional
`intro_candidate`, `groove_candidate`, `build_candidate`, `breakdown_candidate`,
`drop_candidate` or `outro_candidate` labels with heuristic evidence strength. These
labels are candidates for later policy, not ground-truth arrangement annotations and not
a musical-quality score. Missing/unreliable grid alignment is never promoted to a phrase
claim. `profile_from_map()` is pure and suitable for quick downstream queries; the
path-based `phrase_profile()` may fingerprint, decode and analyse a grid, so it must not
run on the 20 ms audio-render callback.

### Set-level musical planning (#405)

The graph remains the technical feasibility boundary: a set candidate must be
an edge already measured to lock by `mixcheck`. `utils/audio/musical_plan.py`
does not change that verdict or turn a preference score into a safety check.
During the background `records_graph.py` build, `setlist.build_profiles()`
loads/builds the cached `songmap.phrase_profile()` evidence; the sets-only
rebuild uses the same path. Neither runs on the 20 ms renderer.

For each measured edge, the planner estimates the outgoing passage near its
exit from the record duration, selected earlier phrase (`back`) and blend
length, and the incoming passage from its cue (`cue`) and blend length. These
are approximate windows from graph metadata, not a second mix measurement.
When both selected windows have counted phrase alignment, the planner can use
their candidate section labels (build, drop, breakdown, groove, intro or outro)
to describe a possible handoff. Unaligned windows can still contribute raw
time-local feature levels, but their section labels are omitted from the set
arc: they are not promoted into counted phrase roles.

The soft assessment looks for complementary section roles and for simultaneous
prominence in bass, sustained midrange/lead proxy, upper-band and transient
activity. Those overlap values are coarse relative-feature diagnostics, not
absolute loudness, vocal detection, stem separation, percussion classification
or a judgment of what a listener will hear. A technically measured pair can be
marked `defer_if_alternative` when its profile proxies look crowded; it remains
eligible as a fallback when the measured graph offers no better route. A
build-to-drop, breakdown-to-drop or drop-to-breath handoff can receive a
purpose explanation. Cross-style changes receive only a small preference when
the available section evidence provides a coherent handoff.

The set arc carries recent coarse roles (settle, groove, lift, peak, breath and
release). It softly spaces repeated peaks, rewards a breathing space after a
peak, and allows a peak after a build or breath; it is not a monotonic BPM ramp
or a fixed warm-up/build/peak template. Candidate ranking first compares this
profile/context preference, then uses the existing blend/key/style/agreement/
artist/stretch ranking. All candidates being ranked are still measured graph
edges. Missing profiles are neutral and preserve the existing ranking.

`graph.json` stores a `set_plans` trace for selected transitions. Each entry
keeps `technical` facts (measured lock, beat count, cue/back, ratio and
agreement) separate from `musical` observations (section candidates, proxy
overlap, purpose, preference and reasons) and the `arc` context. Only selected
transition explanations are persisted; full phrase arrays are not copied into
the graph. `SET_METHOD` is bumped independently of `METHOD`, so changing
playlist preference rebuilds set paths without re-measuring audio edges.

This is the first cached-profile preference layer, not a complete live
"wait for the next phrase" execution policy. In particular, a defer label only
reorders available measured choices; when the graph has no alternative, the
set builder retains the least-bad measured path. There is no vocal separation
or human-confirmed taste model here. Bounded listener-directed next-pick
preferences are implemented separately under [#407](https://github.com/Ekco-S64QTN6/Kaiacord/issues/407).
Unit tests prove deterministic policy behavior on fixtures, not audible
improvement. Real-crate full-set listening and independent assessment remain
mandatory under [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402).

### Records-mode listener direction (#407)

`RecordsSession.request()` is the records-mode entry point for musical
direction. `music_handler.py` routes a `!music` request to the active records
session before considering Strudel; when records is active it does not resolve
or call the Strudel request handler. With no records session, the existing
Strudel `session.request()` behavior is unchanged. A records musical request
does not enter `RecordsSession.requests`, which remains the separate booth
queue for explicit track paths.

`records_intent.py` parses a deliberately bounded vocabulary: more/less bass,
darker/brighter, build/drop, calmer/harder. Each accepted request is typed,
latest-wins, one-shot, and expires after 15 minutes. It steers a future
autonomous pick; it does not immediately change the playing record's EQ,
tempo, faders, or effects. If a next-record choice is already queued, planned,
or being picked, the request is deferred to the following autonomous choice.
A pick worker already in flight when the request arrives is explicitly skipped
using a selection generation, so the response cannot promise to change a
candidate it has already begun choosing.

The preference is soft and positive-evidence-only. For a bounded frontier of
candidates, the picker compares the outgoing and incoming records' approximate
exit/entry windows using the cached phrase profiles in each record's own source
time (tracked/source BPM, not the stretched playback BPM). More/less bass, darker,
brighter and calmer/harder use the corresponding relative feature-level
difference. Build/drop require a counted, phrase-aligned candidate section.
Only a candidate whose score moves meaningfully in the requested direction
may move ahead of the normal selection order; contrary, weak or missing
evidence leaves the precomputed set path and existing candidate ranking intact.
The candidate still goes through the existing transition planner. Any overlap
must pass the existing measured mixcheck; if no blend locks, only the existing
no-overlap echo-out/switch fallback may be used. A request is recorded as selected only
after the incoming deck has been prepared and a plan published; this is a
selection decision, not a claim that audio parameters changed or that a
listener's taste was satisfied.

The feature curves remain limited evidence: bass/upper/full are relative
spectral levels, and the lead curve is not a vocal detector. Transient
activity is not drum or percussion classification. Requests for vocals,
acapella, percussion or drums are declined with an explanation; faster/slower
tempo requests are also declined because this request path does not implement
a tempo change. Missing profiles are neutral, a preference can remain pending
until a later candidate or expire unused, and unsupported requests never fall
through to Strudel while records mode is active. These tests validate routing
and decision bookkeeping, not audible improvement; [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402)
still requires real-crate listening and independent assessment.



### DJ skill catalog and phrase action runner (#406)

`utils/audio/dj_skills.py` is a decision/action layer over controls the records
mixer already renders. Its catalog declares purpose, context, preconditions,
capabilities, phrase timing, parameter bounds, owned lanes, composition,
release/cancellation, fallback and a truthful booth explanation. The first
catalog contains only:

- Counted-section solo moves: build pressure (small low hold-back and upper lift),
  drop reveal (small low emphasis and slight upper reduction), plus explicit
  no-op decisions to let a breakdown breathe or a stable groove ride.
- The existing legacy phrase-EQ gesture as a fallback when no aligned structural
  profile can speak to the current window. Its record-path CRC32 seed is stable
  across process restarts; the profile compiler's fingerprint is installed before
  the first frame and refreshed when a new record takes over.
- The existing blend headroom stage, eight-bar upper-band exchange and outgoing
  air ease. The upper bands trade in opposite directions; no vocal/midrange
  classification or new EQ/DSP bands are inferred.
- The existing finite, measured transition echo-out fallback.
- A separate, manual master-bus tempo echo now runs through `TempoEcho` in the
  buffered renderer. It locks its delay to the on-air playback BPM at activation
  (½, 1, 2 or 4 beats), caps feedback at 0.65 and wet gain at 0.50, ramps
  parameter changes over eight 20 ms frames, and stops accepting input when
  released while a finite six-repeat tail decays. It affects the program/master
  path, not the independent pre-fader PFL cue. It is a real first effect
  primitive, **not** a general multi-effect send/return, an autonomous DJ skill,
  or proof of audible quality on a physical headphone/device chain.

The records profile worker builds/reads the cached phrase profile and compiles at
most 64 solo actions. Its queue has one pending slot and latest-track-wins
generation checks; when a new track becomes current, the prior track's action
timeline is cleared immediately under the source lock before the new profile
can finish. Profile phrase coordinates are source-record seconds. Solo rendering
converts `Deck.at()` stretched-playback seconds back to source time using the
current deck ratio; manual-release ramps stay on the live playback clock.

The transition planner compiles at most four blend actions after the incoming
deck is ready and before its plan is published. In the 20 ms renderer the
scheduler evaluates only these bounded action tuples and NumPy ramps. It does
not open files, fingerprint audio, decode, call models, create threads or run
an unbounded search. It owns no controls the mixer does not expose.

Booth control writes use `CrossfadeSource.set_control()` at the source frame
lock and give the human ownership of the touched EQ/gain lane. Kaia's move on
that lane eases to neutral over one bar and does not resume behind the user's
back. The existing HANDS switch disables/enables the skill scheduler; KAIA MIX
resets the mixer and explicitly clears manual ownership. The skill snapshot
reports the active skill, reason, profile state, catalog and manual overrides.
Each active state exposes its actual lane targets/parameters and action windows;
solo structural skills include the counted four-bar phrase's source-time bounds,
while blend and echo skills report their measured transition window. The booth
renders these values from scheduler state rather than inferring them from labels.

This is a limited first execution layer, not the full skill repertoire in #402.
Because #403 remains open and has not supplied a shared runtime capability registry,
`dj_skills.py` uses a conservative current-engine allowlist and rejects any catalog
entry that asks for a capability outside it. The manual `fx.echo` engine capability
is registered, but no autonomous skill currently owns or schedules it; the operator
alone controls the master echo in the booth. This is an explicit bridge, not a claim
that the future #403 capability model is already integrated. The manual slip-roll primitive
and master echo are real operator controls, but neither is currently an autonomous skill. Do not
advertise roll/beat-juggle compositions, manual jog bends, scratches, filters, stutters or effects
beyond the manual echo as selectable skills or cosmetic controls. Human audition on real records
and independent/blind assessment remain mandatory under #402.

### Crossfader curves and deck assignment (#403, first slice)

`records.Controls` retains the legacy standard law as its default. With deck 1
assigned to A and deck 2 to B, the standard law is exactly the previous behavior:
at the ends one side is attenuated linearly over half the travel, and around the
centre both sides remain full. Existing sessions therefore keep the same sound.

The booth can select three transfer laws: `standard` (legacy overlap),
`constant_power` (A = cos(xπ/2), B = sin(xπ/2), an equal-power pair), and
`cut` (A owns x < 0.5; B owns x ≥ 0.5). Each deck can independently be assigned
to A, B or THRU; THRU bypasses only the crossfader for that deck, not its channel
fader, trim, EQ or master. Assigning both decks to one side is permitted.

Changing curve or deck assignment compiles a new pair of target gains and ramps
from the currently applied pair over eight 20 ms PCM frames with cosine easing.
`Controls.advance_frame()` is called once inside the locked `CrossfadeSource`
render boundary; the booth thread does not advance or interpolate DSP state.
Direct crossfader movement remains immediate to follow the operator's hand, and
the cut law deliberately performs a hard A/B handoff at the midpoint.
Non-finite values and unknown curve/assignment names are rejected. Reset returns
the curve and assignments to standard/A/B and clears the direct crossfader position.

The #403 slices now provide crossfader laws/assignments, a real PFL/cue-monitor signal path, and
persistent one-memory/eight-hot cue banks with frame-safe decoder replacement. PFL uses a separate
decoder, preserves EQ/trim while bypassing channel and crossfader gains, and blends against the rendered
master locally. Hot/memory cues are persisted by stable audio identity and are not catalog metadata.
A real beat-loop path is now implemented for 1/2/4/8 beats on a counted, bar-known on-air deck.
The loop segment is decoded ahead of time into a fixed-size PCM tuple on the booth request thread;
the renderer only indexes that bounded buffer. The loop arms at a two-bar phrase boundary only when no transition is active or being prepared;
that ownership is rechecked after decoding before the loop is committed. It keeps `Deck.played` monotonic
for renderer scheduling, and reports wrapped source position through `Deck.at()`.
Automatic end planning and tempo glide are suspended while the loop owns the deck. Exit warms a normal
decoder at the loop end and commits it at the next wrap boundary; the selected PFL decoder shares the
same loop frames and exits on that same boundary. Hot/memory cue seeks are refused while a loop or
its boundary exit owns the deck, rather than silently replacing the loop clock.

**Momentary slip rolls** are a separate control from a persistent beat loop. The 1/2/4/8-beat
phrase PCM is decoded on the booth request thread and armed for the next counted bar. While the
roll is held, each renderer frame outputs the repeated phrase but also consumes the corresponding
frame from the live program decoder; the monotonic deck clock therefore keeps advancing underneath
the temporary repeat. The selected PFL decoder receives the same predecoded roll and advances its
own live decoder in lockstep, even when no browser headphone stream is currently attached. On
pointer release, the output blends back to the live decoder over four 20 ms frames, at the source
position that would have been reached without the roll. A 600-frame (12-second) hard cap forces
release if pointer-up is lost. Arm requires a counted bar-known on-air deck, no transition/loop/
pause ownership, and enough decoded track remaining for the bounded hold. The renderer does not
seek or decode; predecode stays on the request thread. This is a manual performance primitive,
not yet an autonomous DJ skill or a full beat-juggling skill library.

A real, bounded manual master echo is now an additional #403 primitive. The booth exposes
its tempo subdivision, feedback and wet level; the renderer snapshots its committed state and
applies the PCM delay/feedback path after the program mix. The delay is fixed to the activation
tempo while running, feedback/wet are capped and ramped, release closes the input gate and
lets a finite tail decay, and KAIA MIX/reset cancels it. The PFL CUE signal remains independent;
the MASTER leg hears the effected program. This is one master echo effect, not a general FX
send/return, an automated skill or a substitute for local audio audition.

**Persistent pitch fader** is a separate on-air operator control, bounded to ±8% and ramped
across eight rendered frames. It is composed multiplicatively with the momentary platter jog:
the program and selected PFL decoders consume the same source samples per output sample, and a
jog release returns to the persistent fader setting rather than to unity. The dashboard reports
the combined pitch/tempo and uses the combined source rate for elapsed/remaining estimates.
Newly selected PFL decoders inherit the stable fader rate and catch up through their own resampler
ring; they do not skip raw decoded frames behind the ring's cursor. The transition planner matches
the incoming deck against the effective outgoing BPM while keeping bar/beat positions in decoded
source time, then maps source-clock positions back to PCM frame and sub-frame boundaries. Manual
hand starts use the same mapping. Automatic tempo glide yields while a pitch override is active,
and loop/roll/transition ownership prevents conflicting pitch changes. This is a human-operated
pitch control, not proof of hardware parity or musical quality.

**Live jog / pitch bend** is a separate momentary operator control on the on-air platter.
Clockwise/counterclockwise movement changes decoder sample consumption between 0.92× and
1.08×, so tempo and pitch move together; this is a phase nudge around the persistent
pitch-fader setting, not a second permanent speed control. The resampler uses a lazily prepared, fixed-capacity PCM ring and emits the same
960-sample/20 ms frame shape. Ring allocation happens on the booth request thread before
acquiring the renderer lock. The program and selected PFL decoders receive the same target and
advance their own source clocks at the actual resampling rate; the dashboard playhead, tempo,
pitch and remaining-time estimates use that rate too. A platter release ramps back to the persistent pitch-fader setting over
eight rendered frames. The entire hold is capped at 500 rendered frames (10 seconds), including
time spent crossing the platter centre; an engine timeout and a browser release timer both
return to unity if pointer-up is lost. Pointer cancel, lost capture, blur, page hide and hidden-tab
events also release the gesture. If a page reload loses the original pointer state, the
platter remains available for a one-tap release acknowledgement while **JOG RELEASE** is shown;
pause, skip and KAIA MIX/reset are also explicit hand-back paths. Planning, automatic tempo glide
and solo phrase skills are suspended while the nudge owns the deck; a new bend is refused while
a transition, loop, slip roll, pause, splice or tempo-glide preparation owns the deck. The live source cursor is retained across the temporary rate change, so the
record resumes where the decoder actually advanced to. This remains a human-operated primitive,
not an autonomous pitch-ride skill, scratch, backspin or permanent pitch control. Physical device
latency and musical suitability still require listening.

Further effects (filter, delay variants, reverb, phaser/flanger, stutter/repeat and performance
effects) still need their own bounded DSP, cancellation and recovery paths before exposure.

The `records-browser-tests` Playwright suite opens the actual loopback booth in Chromium and
exercises memory/hot cue store, Shift-click overwrite, filled-pad recall, right-click clear,
loop arm/exit, and the real master-echo on/off and hand-back controls through browser input.
It checks persisted cue state, decoder hand-off, loop state and effect activation/release;
it does not substitute direct HTTP calls for those UI gestures. This fixture verifies the
software path, not a physical headphone/device audition.

### Real-time engineering boundary

Keep the 20 ms Discord audio path bounded. Do not put disk or network I/O, full-track analysis,
unbounded DSP, blocking model inference or expensive planning in the voice callback. Perform
analysis and set planning off the callback using cached/background work; schedule bounded,
sample/phrase-aware operations at safe boundaries, ramp parameters, preserve the mixer's frame
and lock invariants, and always provide manual override and hand-back. The PFL decoder is warmed
on the booth request thread; `CrossfadeSource.read()` only consumes one already-buffered frame and
publishes a fixed-size headphone frame into bounded per-client queues. Hot-cue recall also warms its
replacement decoder on the request thread, commits only after frame-boundary identity checks, and
reaps the old decoder after releasing the lock. Cue-bank disk reads/writes stay in dashboard threads.
Beat-loop audio is also prepared on the request thread, capped at 500 fixed-size frames, then attached
to a deck with a separate loop source clock; `CrossfadeSource.read()` does not seek or decode it. Loop exit
warms the post-loop program and PFL decoders before scheduling a boundary swap. HTTP streaming and
browser playback run on their own threads/processes. Keep the engine's audible
capabilities honest: a planner can only select a skill the mixer can actually execute.

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
  was cut mid-phrase at the swap. **One voice at a time:** a voice is not only mids, so the automix
  splits HIGH in two at `PRESENCE_TOP_HZ` (6 kHz). The presence under it (consonants, what makes a lyric
  a lyric) changes hands with the mids (`presence`: the incoming's at `PRESENCE_HOLD` of its air until
  the handoff, the outgoing's gone after it); only the air above rides early and leaves late. As one band,
  "highs first" brought the new singer in over the old one, and the old one's stayed up after the swap
  (You're So High into For Me (VIP), 13 Nov). The booth's HIGH knob turns both halves.
  **After the swap the outgoing leaves** (`tail`): gone within `TAIL_BEATS` (32) or a quarter of the
  blend, never later than its second half, and `Plan.done` is then — the deck is free and the room
  checks need only that much of the outgoing. A 256-beat blend used to keep it 64 s past the swap.
  A ramp is a quarter of a
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
  - **A short overlap must agree in more of its bars** (`needed`: all of 4, 5 or 6; 6 of 7 or 8). A blend is searched
    for in dozens of places, and a random lag lands inside `AGREE_S` about one time in twelve.
  - **A far move needs most of the shared kicks behind it** (`mixcheck.move_refused`). A blend moved
    0.18 beat or more (`FAR_MOVE`) is made only when 0.8 of the bars where both records have a kick agree
    on the lag and at least four do; a lag within a tenth of the search's quarter-beat reach (`EDGE`) moves
    nothing, because the best alignment may lie beyond it. Smaller moves correct the tracker as before. In
    402 journalled blends, 13 sat at the edge and 14 were moved far on one shared kick or on eleven bars of
    sixteen (the one heard as rough). On 30 far-moved pairs of the library 21 still lock, 17 of them
    somewhere else; 10 of 10 near-moved pairs are unchanged. The search goes on to its other places when
    a move is refused.
  - **Search before giving up** (`setlist.find_blend`): the planned spot, the incoming cued at another
    phrase (bar 0/8/16/32), the outgoing mixed out up to five 8-bar phrases earlier (a skip: up to three
    4-bar phrases later), then 32 and 16 beats. The planner gives it `SEARCH_S`.
  Check a judge change on click tracks *and* on real pairs in the band you did not measure: a lock is
  only as good as what plays in the bars the judge left out. It cannot always tell a kick from a heavy
  rolling bassline on the beat; that needs ears.
- **She leaves a record where it changes, and near its end** (`songmap`, `setlist.find_blend`,
  `CrossfadeSource._swaps`). `songmap` holds three curves per record against its own usual level —
  everything, the low end, and what is up front in the mids (centre of the stereo picture, 300-3400 Hz,
  drum hits taken out; not a vocal detector) — cached in `memory/records/maps/`, a second or two of
  NumPy per record, no model. From them: where its **outro** starts (the last stretch to the end of
  its music with the lead gone; 157 of 347 records have one, median 31 s) and where its **last
  breakdown** starts (low end gone for 8 bars or more, past 60% of the record). An end-of-record blend
  is tried with the bass swap on the phrase nearest the outro's start first (`plan_transition(swap_at=)`),
  so the outro is not played out; with the energy for it (`BREAK_ENERGY`), and for one record in three
  whatever her mood, the breakdown comes first. The record on air is scouted when it takes over
  (`_scout`, its own thread) and planned that much earlier (`_plan_ahead`). Then the old search, in a
  new order: a real blend (32 beats or more) with the outgoing gone no more than `NEAR_END_S` (75 s)
  before its music ends, then the 16-beat one there, and only then anywhere further back. The old order
  took the first lock walking back from the end at the longest length: a 64-beat blend two minutes early
  beat a 32-beat one on the last phrase, and records were left mid-verse (Running Up That Hill after
  55 s, 13 Nov) with the next one's vocal over theirs. Keys more than a step apart get the 32-beat
  blend first (`blend_lengths`). The journal's `where`, `swap` and `gone` say what was chosen.
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
- **She picks partners with a musical purpose, within the measured graph** (`musical_plan`,
  `setlist.make_sets`). The existing blend/key/style/agreement rank remains the technical-choice
  tie-breaker; cached phrase-profile evidence adds a soft local complement/clutter preference and a
  recent-role arc adjustment. Build→drop, breakdown→drop and peak→breath can explain a handoff; repeated
  peaks are spaced and a breathing space after a peak is preferred. A crowded pair is deferred when another
  measured edge exists, not deleted from the graph. Missing profiles are neutral. The `set_plans` record
  separates measured lock facts from musical proxy observations and contextual reasons. This is not yet a
  live phrase-wait policy, vocal detector or proof of taste; [#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402)
  still requires real-crate listening and independent assessment. `SET_METHOD` versions these preference
  changes separately from `METHOD`, so set paths rebuild without re-measuring audio edges.
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
selects a separate decoder for the chosen deck; its PFL tap applies channel EQ and trim before the channel
fader, crossfader and program master. It never consumes the program deck's decoder frames. The browser hears
that cue and the rendered program through a local 48 kHz stereo PCM stream (`/phones/stream`), with an
equal-power CUE-to-MASTER blend and an independent monitor level. A browser AudioWorklet consumes the
bounded 20 ms frames; per-client queues are capped at 50 frames and drop the oldest frame under backpressure.
The monitor is local to the booth and is never sent back to Discord. The older `/audio/<id>` file endpoint is
not used for PHONES. The deck CUE button temporarily selects PFL while held. Kaia raises a hand-loaded
fader when *her* blend into it starts, not when she plans it — a planned blend is called off by ▶.

Each loaded deck exposes one memory cue and eight hot cues. Their source-time positions are persisted
outside `dj_catalog.json`, in `memory/records/cues.json`, keyed by `audio_identity.audio_signature` rather
than the filename or editable tags. Empty-pad click stores the current source position; clicking a filled
pad jumps there; Shift-click overwrites; right-click clears. Recall warms a replacement decoder on the
booth request thread, verifies the deck identity again, and swaps it at a frame boundary. It refuses a
transition that has already started and never seeks by consuming frames from the program decoder.
Cue-bank reads and atomic writes run on dashboard threads, not the renderer. The Playwright
acceptance suite covers cue gestures, beat-loop arm/exit and master-echo activation/release in
Chromium against a deterministic real mixer session. It does not establish physical headphone
routing, device latency or artistic suitability; those still require local audition.
A cue set on the record already in her plan (she plans a record's end minutes ahead) calls that plan
off and replans from the cue; it used to be refused, and the jog snapped back to the start. A knob's
pointer is what is *applied* — the hand's setting times the automix and her hands — so her moves turn
it; the hand's own setting is the yellow dot, and a deck not sounding shows the hand's setting. Her own
multipliers are streamed apart from the automix (`hands_now`), and a knob she is holding turns pink — a ring,
an arc from where it would be without her, and a dB badge — or she visibly does nothing (the page has a
`.kaia` grid class; a knob marked with it collapsed the mixer column).
The header **FX** pill (remembered per browser, off under reduced motion) remains a visual
stage built only from the stream; it is not an audio effect control. The separate **AUDIO FX**
row exposes the real tempo-synchronised master echo and reports enabled/tail state from the
renderer snapshot. The visual stage is a floor and horizon on the beat of the record on air,
level bars from the applied bands, a reticle zooming onto
each knob Kaia's hand is on with sparks the way she turns it, an aura and combo that build through locked blends
(LOCKED on a measured blend, BASS SWAP, PERFECT BLEND when one finishes), ECHO OUT in purple on an echo-out (it
neither adds to the combo nor breaks it), and red — vignette, glitch, shake, combo broken — on a late voice frame.
The floor is one of five scenes (mountains, pyramids, city, ocean, tunnel) travelling toward the horizon at the
beat, picked at load and crossfaded to another on each new record. The mixer's meters and the two scrolling lanes are drawn every animation
frame. Meters and playheads are timed by `heard`, the frame the voice thread is handing to Discord
(`frames_sent` less what waits in the audio buffer), mapped to the page's clock; SYNC +N ms (160 by
default) adds what Discord takes to play it. Timed by the newest rendered frame they ran 250 ms ahead
of the sound, and 4-5% of the frames a meter wanted had not arrived yet and were skipped (the bar fell
and jumped). The stream is paced by a deadline, and the snapshot reads her mood before taking the
mixer's lock. Her avatar is WebGL: where the browser has no GPU acceleration (`softwareGL`) it runs at
6 fps, since drawn on the CPU at 30 it took over three cores from every other canvas.
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
