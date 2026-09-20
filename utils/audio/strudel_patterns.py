"""
Genres as narrated live-coding performances.

Each genre is a set of lanes plus a *script of edits*: bring a part in, chain an
effect onto a line that is already playing, nudge one number, solo something,
take a part away. The build order and the kinds of edit follow Switch Angel's
narrated Strudel sets, where almost every move is a small change to a line that
is already sounding:

    "tame with an acid slider" · "duck it with our kick" · "lower the depth of
    the duck to 0.8" · "lower the decay" · "destroy the bass with diode
    distortion" · "FM the bass with time" · "drop the bass to F1" · "add 30
    semitones" · "random detune for more power" · "isolate the lead" ·
    "turn our hi-hats into an infinite riser" · "bring in the angels"

Two functions in those videos are her own and do not exist in Strudel:
`trancegate` is written here as `tremolosync`/`tremolodepth`/`tremoloshape`,
and `rlpf(x)` as `lpf(x).lpq(n)`.

Everything else is verified present in the bundle before use —
tools/maintenance/verify_strudel_patterns.py plays every step of every script
and measures the audio, because a pattern Strudel cannot parse fails silently.
"""

from utils.audio.performance import ADD, CLEAR, DROP, FX, SET, SOLO

# Slider ranges are exposed so a human can ride them in the editor while Kaia
# plays; she writes slider(x, lo, hi) and only ever changes x.
GENRES: dict[str, dict] = {
    'trance': {
        "bpm": '~138', "cpm": '138/4',
        "blurb": 'supersaw trance: acid bass, ducked gates, riser, breakdown',
        "lanes": {
            'kick': 's("bd*4").gain(0.95).o(1)._scope().color("#f472b6")',
            'bass': 'n("0*16").add(n("<0 -2 -4 0>*2")).scale("g2:minor").s("supersaw").o(3).color("#fb923c")._scope()',
            'hats': 's("hh*8").gain(0.22).o(2).color("#94a3b8")',
            'clap': 's("~ cp").gain(0.4).room(0.3).o(2).color("#cbd5e1")',
            'lead': 'n("<0 4 0 9 7>*16").scale("g4:minor").s("supersaw").o(4).color("#facc15")._pianoroll()',
            'pad': 'n("<0,3,7 -2,2,5 -4,0,3 0,3,7>*2").scale("g3:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
            'riser': 's("hh*16").gain(0.14).o(6).color("#94a3b8")',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("g4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.34).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick drum, four on the floor'},
            {"op": ADD, "lane": 'bass', "seconds": 16, "say": 'next, bass'},
            {"op": FX, "lane": 'bass', "arg": '.lpf(slider(0.35,0,1).range(180,2600)).lpq(8)', "seconds": 18, "say": 'tame it with an acid slider'},
            {"op": FX, "lane": 'bass', "arg": '.attack(0.01).decay(0.16).sustain(0.08).release(0.18)', "seconds": 14, "say": 'tighten the envelope'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.5).duckattack(0.14)', "seconds": 16, "say": 'duck it with our kick'},
            {"op": SET, "lane": 'bass', "arg": 'duckdepth', "value": '0.8', "seconds": 14, "say": 'lower the depth of the duck to 0.8'},
            {"op": FX, "lane": 'bass', "arg": '.detune(rand)', "seconds": 14, "say": 'random detune for more power'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'white noise hi-hats'},
            {"op": FX, "lane": 'hats', "arg": '.dec(tri.range(0.03,0.14).slow(7))', "seconds": 16, "say": 'decay modulated with a triangle wave'},
            {"op": ADD, "lane": 'lead', "seconds": 20, "say": 'our lead will be a supersaw'},
            {"op": FX, "lane": 'lead', "arg": '.lpf(slider(0.5,0,1).range(500,5200)).lpq(2)', "seconds": 16, "say": 'acid slider on the lead'},
            {"op": FX, "lane": 'lead', "arg": '.attack(0.01).decay(0.2).sustain(0.15).release(0.8)', "seconds": 14, "say": 'give it a tail'},
            {"op": FX, "lane": 'lead', "arg": '.delay(0.4).delaytime(0.1875).delayfeedback(0.55)', "seconds": 16, "say": 'we need more power with delay'},
            {"op": FX, "lane": 'lead', "arg": '.pan(rand)', "seconds": 14, "say": "let's make it swirl with random panning"},
            {"op": ADD, "lane": 'clap', "seconds": 16, "say": 'clap, to increase the harmonic tilt'},
            {"op": ADD, "lane": 'pad', "seconds": 18, "say": 'bring the pad underneath'},
            {"op": FX, "lane": 'pad', "arg": '.attack(1.2).release(3).lpf(perlin.range(400,1800)).lpq(0)', "seconds": 16, "say": 'slow it right down'},
            {"op": FX, "lane": 'pad', "arg": '.duck("1").duckdepth(0.55)', "seconds": 16, "say": 'duck the pad too'},
            {"op": SET, "lane": 'lead', "arg": 'lpq', "value": '6', "seconds": 14, "say": 'increase the power of our filter'},
            {"op": SOLO, "lane": 'lead', "seconds": 22, "say": 'isolate the lead'},
            {"op": CLEAR, "seconds": 16, "say": 'and bring it all back'},
            {"op": SET, "lane": 'lead', "arg": 'n', "value": '"<0 3 5 7 10 7 5 3>*16"', "seconds": 18, "say": 'rewrite the lead — same key, new figure'},
            {"op": DROP, "lane": 'kick', "seconds": 20, "say": 'breakdown — drop the kick'},
            {"op": DROP, "lane": 'hats', "seconds": 18, "say": 'just the pad and the lead'},
            {"op": ADD, "lane": 'riser', "seconds": 16, "say": 'an infinite riser'},
            {"op": FX, "lane": 'riser', "arg": '.dec(0.08).fm(time).fmh(time)', "seconds": 16, "say": 'FM it with time'},
            {"op": ADD, "lane": 'kick', "seconds": 20, "say": 'bring our kick back in'},
            {"op": SET, "lane": 'pad', "arg": 'n', "value": '"<0,3,7 -5,-1,2 -4,0,3 -2,2,5>*2"', "seconds": 16, "say": 'turn the chords around underneath it'},
            {"op": ADD, "lane": 'hats', "seconds": 18, "say": 'and the hats'},
            {"op": FX, "lane": 'lead', "arg": '.fm(0.5).fmwave("brown")', "seconds": 18, "say": 'FM the supersaw with noise for more chaos'},
            {"op": SET, "lane": 'bass', "arg": 'lpq', "value": '12', "seconds": 16, "say": 'more power on the bass'},
            {"op": DROP, "lane": 'riser', "seconds": 22, "say": 'let it ride'},
            {"op": ADD, "lane": 'vox', "seconds": 18, "say": "bring in the angels"},
            {"op": FX, "lane": 'vox', "arg": '.delay(0.5).delaytime(0.375).delayfeedback(0.5).pan(rand)', "seconds": 16, "say": 'scrub it like a tape loop'},
            {"op": DROP, "lane": 'lead', "seconds": 18, "say": 'take the lead out'},
            {"op": DROP, "lane": 'clap', "seconds": 16, "say": 'and out'},
        ],
    },

    'house': {
        "bpm": '~124', "cpm": '124/4',
        "blurb": 'house: 909 kit, off-beat open hat, filtered stabs, rolling bass',
        # A house record opens on a groove, not on a kick by itself. The first
        # move brings four lanes up together; the build after that is about
        # colour, not about whether there is a track yet.
        "lanes": {
            'kick': 's("bd*4").bank("RolandTR909").gain(0.92).o(1)._scope().color("#f472b6")',
            'clap': 's("~ cp").bank("RolandTR909").gain(0.42).room(0.22).o(2).color("#cbd5e1")',
            'hats': 's("[~ hh]*4").bank("RolandTR909").gain(0.28).o(2).color("#94a3b8")',
            # The off-beat open hat is the sound that says "house" more than
            # anything else in the kit.
            'open': 's("~ oh ~ oh").bank("RolandTR909").gain(0.17).o(2).color("#94a3b8")',
            'shaker': 's("hh:2*8").bank("RolandTR909").gain(0.09).degradeBy(0.3).pan(rand).o(2).color("#94a3b8")',
            # Rolling bass with a filter envelope (lpa/lpd/lpenv) rather than a
            # bare sawtooth. That envelope is the house bass sound, so it belongs
            # in the opening move, not several edits in.
            'bass': 'note("<c2 [c2 c2] g1 [a#1 c2]>*2").s("sawtooth").lpf(620).lpq(8).lpa(0.02).lpd(0.12).lpenv(3).attack(0.01).decay(0.14).sustain(0.06).release(0.12).gain(0.8).o(3).color("#fb923c")._scope()',
            # Real 7th-chord voicings with voice leading, struck on the
            # off-beats. `n(...).scale(...)` triads were the thin sound.
            'stabs': 'chord("<Cm7 Fm7 Ab^7 Gm7>").voicing().anchor("c5").struct("~ x ~ x ~ x ~ x").s("sawtooth").attack(0.005).decay(0.18).sustain(0).release(0.12).lpf(2000).lpq(5).gain(0.4).room(0.3).o(4).color("#5eead4")._spectrum()',
            'pad': 'chord("<Cm7 Fm7 Ab^7 Gm7>").voicing().anchor("c4").s("supersaw").attack(1.4).release(2.6).lpf(900).lpq(0).gain(0.2).room(0.6).o(5).color("#38bdf8")._spectrum()',
            'top': 'n("<12 15 12 19>*8").scale("c5:minor").s("triangle").gain(0.16).degradeBy(0.6).pan(rand).room(0.6).delay(0.4).o(6).color("#a78bfa")._pianoroll()',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("c4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.28).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'kick, hats, clap, bass', "seconds": 16, "say": 'four to the floor, hats and bass together'},
            {"op": ADD, "lane": 'open', "seconds": 13, "say": 'open hat on the off-beat'},
            {"op": ADD, "lane": 'stabs', "seconds": 16, "say": 'chord stabs between the beats'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.7).duckattack(0.12)', "seconds": 15, "say": 'duck the bass with the kick'},
            {"op": FX, "lane": 'stabs', "arg": '.lpf(slider(0.45,0,1).range(700,4000)).lpq(5)', "seconds": 16, "say": 'put the stabs on a filter'},
            {"op": ADD, "lane": 'shaker', "seconds": 14, "say": 'shaker for the top end'},
            {"op": FX, "lane": 'hats', "arg": '.swingBy(1/3, 4)', "seconds": 15, "say": 'swing the hats a third'},
            {"op": ADD, "lane": 'pad', "seconds": 17, "say": 'a pad underneath the whole thing'},
            {"op": FX, "lane": 'pad', "arg": '.duck("1").duckdepth(0.5)', "seconds": 14, "say": 'let the kick breathe through it'},
            {"op": FX, "lane": 'stabs', "arg": '.off(0.125, x => x.gain(0.22).pan(0.7))', "seconds": 16, "say": 'echo the stabs an eighth behind'},
            {"op": SET, "lane": 'bass', "arg": 'lpenv', "value": '5', "seconds": 14, "say": 'more movement in the bass filter'},
            {"op": ADD, "lane": 'top', "seconds": 16, "say": 'a sparkle up high'},
            {"op": DROP, "lane": 'kick, bass', "seconds": 16, "say": 'breakdown — drop the bottom out'},
            {"op": FX, "lane": 'pad', "arg": '.room(0.85).lpf(1600)', "seconds": 15, "say": 'open the pad right up'},
            {"op": ADD, "lane": 'vox', "seconds": 15, "say": 'a vocal in the gap'},
            {"op": FX, "lane": 'vox', "arg": '.rev().delay(0.4).delaytime(0.5).room(0.5).pan(rand)', "seconds": 14, "say": 'reverse and echo it'},
            {"op": ADD, "lane": 'kick, bass', "seconds": 18, "say": 'and everything back in'},
            {"op": SET, "lane": 'stabs', "arg": 'lpq', "value": '9', "seconds": 15, "say": 'more bite on the stabs'},
            {"op": SET, "lane": 'stabs', "arg": 'chord', "value": '"<Cm7 Ab^7 Fm7 G7>"', "seconds": 12, "say": 'turn the progression around'},
            {"op": SET, "lane": 'pad', "arg": 'chord', "value": '"<Cm7 Ab^7 Fm7 G7>"', "seconds": 16, "say": 'and bring the pad with it'},
            {"op": SOLO, "lane": 'stabs', "seconds": 15, "say": 'just the chords for a moment'},
            {"op": CLEAR, "seconds": 18, "say": 'full groove'},
            {"op": DROP, "lane": 'top, vox', "seconds": 15, "say": 'thin it out'},
            {"op": DROP, "lane": 'shaker, open', "seconds": 14, "say": 'and out'},
        ],
    },

    'techno': {
        "bpm": '~134', "cpm": '134/4',
        "blurb": 'driving techno: acid line, hard kick, long filter builds',
        "lanes": {
            'kick': 's("bd*4").gain(1.0).o(1)._scope().color("#f472b6")',
            'hats': 's("[~ hh]*4").gain(0.26).o(2).color("#94a3b8")',
            'ticks': 's("hh:3*8").gain(0.13).pan(rand).o(2).color("#94a3b8")',
            'clap': 's("~ ~ cp ~").gain(0.35).room(0.35).o(2).color("#cbd5e1")',
            'acid': 'n("{0 0 3 0 5 0 7 3}%16").scale("a2:minor").s("sawtooth").o(3).color("#facc15")._pianoroll()',
            'sub': 'n("0*8").add(n("<0 -2>*2")).scale("a1:minor").s("supersaw").o(4).color("#fb7185")._scope()',
            'pad': 'n("<0,3,7 -2,2,5>*2").scale("a4:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("a4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.26).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'kick', "seconds": 20, "say": 'kick, four on the floor'},
            {"op": ADD, "lane": 'sub', "seconds": 16, "say": 'sub underneath'},
            {"op": FX, "lane": 'sub', "arg": '.detune(rand).attack(0.01).decay(0.3).release(0.25).lpf(220).lpq(0)', "seconds": 16, "say": 'keep it low'},
            {"op": FX, "lane": 'sub', "arg": '.duck("1").duckdepth(0.65)', "seconds": 16, "say": 'duck it'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": ADD, "lane": 'acid', "seconds": 18, "say": 'the acid line'},
            {"op": FX, "lane": 'acid', "arg": '.attack(0.005).decay(0.1).sustain(0.04).release(0.16)', "seconds": 14, "say": 'short and snappy'},
            {"op": FX, "lane": 'acid', "arg": '.lpf(slider(0.28,0,1).range(220,3200)).lpq(9)', "seconds": 18, "say": 'tame it with an acid slider'},
            {"op": FX, "lane": 'acid', "arg": '.delay(0.28).delaytime(0.1875).delayfeedback(0.5)', "seconds": 16, "say": 'delay for power'},
            {"op": FX, "lane": 'acid', "arg": '.duck("1").duckdepth(0.7).duckattack(0.1)', "seconds": 16, "say": 'duck against the kick'},
            {"op": ADD, "lane": 'clap', "seconds": 16, "say": 'clap'},
            {"op": ADD, "lane": 'ticks', "seconds": 16, "say": 'ticks on top'},
            {"op": SET, "lane": 'acid', "arg": 'lpq', "value": '13', "seconds": 16, "say": 'more resonance'},
            {"op": FX, "lane": 'acid', "arg": '.distort(1.6)', "seconds": 18, "say": 'destroy it with distortion'},
            {"op": SOLO, "lane": 'acid', "seconds": 20, "say": 'isolate the acid'},
            {"op": CLEAR, "seconds": 18, "say": 'all back in'},
            {"op": SET, "lane": 'acid', "arg": 'n', "value": '"{0 3 0 7 0 10 7 3}%16"', "seconds": 18, "say": 'rewrite the acid figure'},
            {"op": DROP, "lane": 'kick', "seconds": 18, "say": 'breakdown'},
            {"op": ADD, "lane": 'pad', "seconds": 18, "say": 'a pad in the gap'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand).attack(1.5).release(4).lpf(perlin.range(500,2000)).lpq(0).room(0.8)', "seconds": 18, "say": 'wide and slow'},
            {"op": ADD, "lane": 'kick', "seconds": 20, "say": 'kick back'},
            {"op": SET, "lane": 'acid', "arg": 'lpq', "value": '6', "seconds": 16, "say": 'pull the resonance back'},
            {"op": FX, "lane": 'acid', "arg": '.fm(0.4).fmwave("brown")', "seconds": 18, "say": 'FM it with noise'},
            {"op": ADD, "lane": 'vox', "seconds": 16, "say": "a voice in the machine"},
            {"op": FX, "lane": 'vox', "arg": '.speed(0.8).delay(0.5).delaytime(0.1875).pan(rand)', "seconds": 16, "say": 'pitch it down and delay it'},
            {"op": DROP, "lane": 'ticks', "seconds": 18, "say": 'thin out'},
            {"op": DROP, "lane": 'clap', "seconds": 16, "say": 'and out'},
        ],
    },

    'drumnbass': {
        "bpm": '~174', "cpm": '174/4',
        "blurb": 'fast breakbeat, deep sub, atmospheric pads',
        "lanes": {
            'pad': 'n("<0,3,7 0,3,7 -2,2,5 <-4,0,3 0,5,8>>*4").scale("d4:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
            'sub': 'n("<0 0 5 3>*4").scale("d1:minor").s("sine").o(3).color("#fb7185")._scope()',
            'kick': 's("bd ~ ~ ~ ~ ~ bd ~").gain(0.9).o(1)._scope().color("#f472b6")',
            'snare': 's("~ ~ ~ ~ sd ~ ~ ~").gain(0.62).room(0.2).o(2).color("#cbd5e1")',
            'hats': 's("hh*8").gain(0.18).pan(rand).o(2).color("#94a3b8")',
            'ghost': 's("hh:4*16").gain(0.1).degradeBy(0.4).o(2).color("#94a3b8")',
            'bells': 'n("<12 15 19 17>*8").scale("d5:minor").s("triangle").o(6).color("#a78bfa")._pianoroll()',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("d4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.3).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'pad', "seconds": 20, "say": 'open on a pad'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand.range(0,0.35)).attack(0.8).release(3).lpf(perlin.range(500,1900)).lpq(0).room(0.85)', "seconds": 18, "say": 'wide and slow'},
            {"op": ADD, "lane": 'sub', "seconds": 16, "say": 'sub bass'},
            {"op": FX, "lane": 'sub', "arg": '.attack(0.01).decay(0.6).sustain(0.4).release(0.35).lpf(170)', "seconds": 14, "say": 'keep it deep'},
            {"op": ADD, "lane": 'kick', "seconds": 16, "say": 'the break'},
            {"op": ADD, "lane": 'snare', "seconds": 16, "say": 'snare'},
            {"op": FX, "lane": 'sub', "arg": '.duck("1").duckdepth(0.5).duckattack(0.08)', "seconds": 16, "say": 'duck the sub'},
            {"op": ADD, "lane": 'hats', "seconds": 18, "say": 'hats'},
            {"op": ADD, "lane": 'ghost', "seconds": 16, "say": 'ghost notes'},
            {"op": ADD, "lane": 'bells', "seconds": 18, "say": 'bells over the top'},
            {"op": FX, "lane": 'bells', "arg": '.degradeBy(0.8).attack(0.01).release(1.6).pan(rand).room(0.9).delay(0.5).delaytime(0.375)', "seconds": 18, "say": 'scatter them'},
            {"op": SOLO, "lane": 'pad', "seconds": 18, "say": 'isolate the pad'},
            {"op": CLEAR, "seconds": 18, "say": 'and back'},
            {"op": DROP, "lane": 'kick', "seconds": 18, "say": 'breakdown'},
            {"op": DROP, "lane": 'snare', "seconds": 16, "say": 'strip it'},
            {"op": DROP, "lane": 'hats', "seconds": 16, "say": 'just pad and bells'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'break returns'},
            {"op": ADD, "lane": 'snare', "seconds": 16, "say": 'snare back'},
            {"op": ADD, "lane": 'hats', "seconds": 20, "say": 'full'},
            {"op": SET, "lane": 'bells', "arg": 'n', "value": '"<12 17 15 19 22 19 15 12>*8"', "seconds": 18, "say": 'move the bells up the scale'},
            {"op": FX, "lane": 'pad', "arg": '.fm(0.3).fmwave("brown")', "seconds": 18, "say": 'noise in the pad'},
            {"op": ADD, "lane": 'vox', "seconds": 18, "say": "bring in the vocal"},
            {"op": FX, "lane": 'vox', "arg": '.delay(0.55).delaytime(0.375).room(0.6).pan(rand)', "seconds": 16, "say": 'throw it into the delay'},
            {"op": FX, "lane": 'sub', "arg": '.lpf(slider(0.3,0,1).range(120,600)).lpq(2)', "seconds": 16, "say": 'put a slider on the sub'},
            {"op": SET, "lane": 'sub', "arg": 'lpq', "value": '6', "seconds": 16, "say": 'more bite on the sub'},
            {"op": FX, "lane": 'snare', "arg": '.delay(0.3).delaytime(0.375)', "seconds": 16, "say": 'delay on the snare'},
            {"op": SET, "lane": 'pad', "arg": 'lpq', "value": '3', "seconds": 16, "say": 'edge on the pad'},
            {"op": DROP, "lane": 'ghost', "seconds": 18, "say": 'thin'},
            {"op": DROP, "lane": 'bells', "seconds": 16, "say": 'out'},
        ],
    },

    'ambient': {
        "bpm": '~60', "cpm": '60/4',
        "blurb": 'generative modular ambient: fourteen voices, polyrhythmic gates, cross-modulated',
        # A rack, not a patch. Fourteen voices in five sections, each gated on a
        # euclidean rhythm of a different length — 8, 9, 11, 12, 13 and 16 steps
        # — so the gates only all agree again after their common multiple, and
        # every filter, pan, gain and gate probability rides its own LFO at its
        # own prime. That is where the "wall of patch cables" actually lives:
        # not in more notes, but in nothing sharing a clock with anything else.
        #
        # Modular equivalents, one per rack function:
        #   sample & hold ....... rand.segment(n)
        #   chaos generator ..... perlin at distinct primes
        #   quantizer ........... .scale(...) — random volts forced in key
        #   shift register ...... irand.segment(8), morphed by someCyclesBy
        #   clock dividers ...... euclid lengths 8/9/11/12/13/16
        #   probability gate .... .degradeBy(p), p itself under an LFO
        #   logic AND ........... .mask(clock)
        #   bernoulli gate ...... someCyclesBy routing to a bright or dark path
        #   bucket brigade ...... .off() cascades and .echo()
        #   stereo field ........ .jux(rev), .pan(perlin) per voice
        # One-off events, re-rolled every pass so the surprises are never in
        # the same place twice. Kept musical rather than destructive: this has
        # to survive an hour of listening, not win a demo.
        "events": [
            {"op": FX, "lane": 'turing1', "arg": '.fast(2)', "seconds": 18, "say": 'double-time the first sequencer'},
            {"op": FX, "lane": 'turing2', "arg": '.slow(2)', "seconds": 20, "say": 'and halve the second'},
            {"op": FX, "lane": 'arp', "arg": '.rev()', "seconds": 18, "say": 'run the arpeggio backwards'},
            {"op": FX, "lane": 'bells', "arg": '.add(note(7))', "seconds": 18, "say": 'lift the bells a fifth'},
            {"op": FX, "lane": 'pings', "arg": '.delayfeedback(0.88).delaytime(0.5)', "seconds": 20, "say": 'let the pings run away with themselves'},
            {"op": FX, "lane": 'chorale', "arg": '.hpf(700).gain(0.14)', "seconds": 18, "say": 'thin the chorale to a whisper'},
            {"op": FX, "lane": 'droneB', "arg": '.add(note(-12))', "seconds": 20, "say": 'drop the second drone an octave'},
            {"op": FX, "lane": 'wind', "arg": '.lpf(perlin.range(900,5200).slow(7)).gain(0.18)', "seconds": 18, "say": 'open the wind right up'},
            {"op": FX, "lane": 'swell', "arg": '.jux(rev)', "seconds": 18, "say": 'mirror the choir'},
            {"op": SOLO, "lane": 'pings', "seconds": 14, "say": 'everything drops but the pings'},
            {"op": FX, "lane": 'turing1', "arg": '.sometimesBy(0.4, ply("2"))', "seconds": 18, "say": 'stutter some of the sequence'},
            {"op": FX, "lane": 'boxes', "arg": '.iter(4)', "seconds": 18, "say": 'rotate the marimba figure'},
            {"op": DROP, "lane": 'droneA, droneB', "seconds": 16, "say": 'pull the bed out from under it'},
            {"op": FX, "lane": 'shimmer', "arg": '.echo(5, 0.125, 0.7)', "seconds": 18, "say": 'cascade the shimmer'},
        ],
        "variants": {
            # A five-semitone span, not nine. Transposing the whole rack moves
            # the sub's fundamental with it, and c1 (33Hz) against a1 (55Hz) is
            # most of a 2.5x swing in measured level between passes — the music
            # audibly getting louder and quieter every seven minutes. Keeping
            # the roots close holds the bottom end in one band.
            "key": ["c", "c#", "d", "d#", "f"],
            "mode": ["minor", "minor:pentatonic", "dorian", "lydian"],
            # Measured RMS at identical gain, so a swap can hold its loudness
            # instead of leaping out or disappearing.
            "swap": {
                "struck": {"gm_kalimba": 0.0141, "gm_vibraphone": 0.0703, "gm_music_box": 0.0359},
                "bell": {"gm_celesta": 0.0715, "gm_tubular_bells": 0.0140, "gm_glockenspiel": 0.0085},
                "pad": {"gm_pad_warm": 0.0446, "gm_pad_new_age": 0.0482,
                        "gm_pad_halo": 0.0592, "gm_pad_bowed": 0.0373},
                "crystal": {"gm_fx_crystal": 0.0211, "gm_fx_brightness": 0.0409,
                            "gm_fx_echoes": 0.0623},
                "choir": {"gm_choir_aahs": 0.0396, "gm_voice_oohs": 0.0496,
                          "gm_synth_choir": 0.0592},
                "noise": {"pink": 0.0358, "brown": 0.0109, "white": 0.0329},
            },
            "masks": ["<1 0 1 1 0 1 1 0>", "<1 1 0 1 0 0 1 1>", "<1 0 0 1 1 0 1 0>",
                      "<1 1 1 0 1 0 0 1>", "<1 0 1 0 1 1 0 1>"],
            "euclids": ["(3,8)", "(5,13)", "(7,16)", "(4,9)", "(5,11)", "(7,12)", "(3,11)"],
            "primes": ["slow"],
        },
        "lanes": {
            # ── bed ──────────────────────────────────────────────────
            'droneA': 'note(choose("c2","g1","eb2").slow(23)).segment(1).s("gm_pad_warm,gm_fx_atmosphere:0:0.5").vib(0.25).vibmod(0.12).attack(3).release(9).lpf(perlin.range(300,900).slow(29)).lpq(0).gain(0.21).pan(0.35).room(0.3).roomsize(9).roomlp(3800).o(1)._scope().color("#fb7185")',
            'droneB': 'note(choose("g2","c3","bb2").slow(17)).segment(1).slow(3).s("gm_pad_bowed").unison(3).spread(0.6).detune(0.12).attack(5).release(12).lpf(perlin.range(260,780).slow(37)).gain(0.15).pan(0.65).room(0.32).roomsize(9).roomlp(3400).o(1).color("#f87171")',
            'sub': 'note(choose("c1","g1","eb1").slow(19)).segment(1).slow(2).s("sine,square:0:0.12").add(note("0,.07")).attack(4).release(11).lpf(200).gain(0.21).room(0.16).roomsize(6).o(1).color("#fb7185")._scope()',

            # ── harmonic field ───────────────────────────────────────
            'swell': 'n(rand.slow(17).segment(1).range(0,7)).slow(3).scale("c3:minor:pentatonic").s("gm_choir_aahs,gm_pad_halo:0:0.4").unison(3).spread(0.5).detune(0.1).attack(5).release(12).lpf(perlin.range(320,1100).slow(19)).lpq(0).pan(perlin.slow(31)).gain(0.17).room(0.28).roomsize(8).roomlp(4200).o(2).color("#38bdf8")._spectrum()',
            'chorale': 'chord("<Cm9 Abmaj7 Fm9 Bbm7>").voicing().anchor("c4").struct("x(3,8)").s("gm_pad_new_age").attack(2).release(7).lpf(perlin.range(400,1600).slow(41)).gain(0.11).pan(perlin.slow(13)).room(0.3).roomsize(8).o(2).color("#60a5fa")',

            # ── sequencers, phasing ──────────────────────────────────
            'turing1': 'n(irand(8).segment(8)).scale("c4:minor:pentatonic").slow(3).s("gm_kalimba").mask("<1 0 1 1 0 1 1 0>").someCyclesBy(0.25, x=>x.add(n(2))).degradeBy(perlin.range(0.35,0.75).slow(13)).clip(2).lpf(slider(0.55,0,1).range(900,5000)).lpq(1).pan(perlin.slow(17)).gain(0.2).room(0.26).roomsize(7).delay(0.5).delaytime(0.6667).delayfeedback(0.65).o(3).color("#facc15")._pianoroll()',
            'turing2': 'n(irand(8).segment(8)).scale("c5:minor:pentatonic").slow(5).s("gm_vibraphone").mask("<1 1 0 1 0 0 1 1>").degradeBy(perlin.range(0.5,0.85).slow(23)).clip(2).jux(rev).lpf(perlin.range(1200,4200).slow(19)).pan(perlin.slow(29)).gain(0.13).room(0.28).roomsize(8).delay(0.4).delaytime(0.75).delayfeedback(0.55).o(3).color("#fbbf24")',
            'arp': 'n("0").off(1/3, add(n(2))).off(1/2, add(n(4))).slow(2).scale("c4:minor:pentatonic").s("gm_music_box").degradeBy(perlin.range(0.45,0.8).slow(31)).clip(2).pan(perlin.slow(11)).gain(0.12).room(0.3).roomsize(8).o(3).color("#fde047")',

            # ── struck, on coprime gates ─────────────────────────────
            'bells': 'n(irand(12).segment(2)).scale("c5:minor:pentatonic").slow(5).s("gm_celesta").degradeBy(perlin.range(0.55,0.9).slow(19)).someCyclesBy(0.5, x=>x.s("gm_tubular_bells").gain(0.6)).clip(3).pan(brand).gain(0.18).room(0.3).roomsize(9).roomlp(6000).delay(0.45).delaytime(0.75).delayfeedback(0.6).o(4).color("#a78bfa")._pianoroll()',
            'pings': 'n(irand(9).segment(1)).scale("c5:minor:pentatonic").struct("x(5,13)").s("gm_glockenspiel").clip(1).degradeBy(perlin.range(0.3,0.7).slow(29)).pan(perlin.slow(23)).gain(0.1).delay(0.62).delaytime(0.8333).delayfeedback(0.76).room(0.3).roomsize(9).o(4).color("#c084fc")',
            'boxes': 'n(irand(6).segment(2)).scale("c3:minor:pentatonic").struct("x(4,9)").s("gm_marimba").clip(2).degradeBy(perlin.range(0.5,0.85).slow(37)).superimpose(x=>x.add(n(7)).gain(0.15).pan(0.8)).pan(0.25).gain(0.1).room(0.28).roomsize(7).o(4).color("#d8b4fe")',

            # ── texture ──────────────────────────────────────────────
            'wind': 's("pink").segment(1).slow(2).attack(4).release(9).lpf(perlin.range(300,1400).slow(31)).lpq(2).hpf(180).gain(0.065).pan(perlin.slow(37)).room(0.3).roomsize(9).o(5).color("#94a3b8")',
            'shimmer': 'n(irand(6).segment(1)).scale("c6:lydian").slow(7).s("gm_fx_crystal").degradeBy(perlin.range(0.6,0.92).slow(23)).attack(1.5).release(6).pan(perlin.slow(29)).gain(0.12).room(0.34).roomsize(9).roomlp(7000).o(5).color("#c4b5fd")._pianoroll()',
            'echoes': 'n(irand(6).segment(1)).scale("c5:lydian").struct("x(3,11)").s("gm_fx_echoes").echo(4, 0.25, 0.55).degradeBy(perlin.range(0.55,0.9).slow(41)).pan(perlin.slow(19)).gain(0.09).room(0.36).roomsize(9).o(5).color("#e9d5ff")',
        },
        "script": [
            # The whole rack is up inside thirty seconds. What follows is the
            # patch being re-patched, not the parts being introduced.
            {"op": ADD, "lane": 'droneA, droneB, sub, swell, turing1, wind', "seconds": 14, "say": 'the bed, the field and the first sequencer'},
            {"op": ADD, "lane": 'chorale, turing2, bells, pings', "seconds": 16, "say": 'second sequencer, chorale, and the gated voices'},
            {"op": ADD, "lane": 'arp, boxes, shimmer, echoes', "seconds": 22, "say": 'everything else — fourteen voices, no shared clock'},
            {"op": SET, "lane": 'turing1', "arg": 'degradeBy', "value": 'perlin.range(0.15,0.55).slow(11)', "seconds": 26, "say": 'open the first probability gate'},
            {"op": SET, "lane": 'pings', "arg": 'struct', "value": '"x(7,16)"', "seconds": 22, "say": 'retime the pings to sixteen'},
            {"op": SET, "lane": 'swell', "arg": 'scale', "value": '"c3:lydian"', "seconds": 26, "say": 'retune the quantizer to lydian'},
            {"op": FX, "lane": 'boxes', "arg": '.jux(rev)', "seconds": 22, "say": 'mirror the marimba across the stereo field'},
            {"op": SET, "lane": 'droneA', "arg": 'lpf', "value": 'perlin.range(200,1400).slow(41)', "seconds": 26, "say": 'widen the drone filter, and slow it right down'},
            {"op": SET, "lane": 'bells', "arg": 'degradeBy', "value": 'perlin.range(0.3,0.7).slow(23)', "seconds": 22, "say": 'let the bells speak more often'},
            {"op": SET, "lane": 'turing2', "arg": 'mask', "value": '"<1 0 0 1 1 0 1 0>"', "seconds": 26, "say": 'change what the second logic gate lets through'},
            {"op": FX, "lane": 'chorale', "arg": '.sometimesBy(0.3, ply("2"))', "seconds": 22, "say": 'double some of the chorale hits'},
            {"op": SET, "lane": 'swell', "arg": 'scale', "value": '"c3:minor:pentatonic"', "seconds": 26, "say": 'back to the pentatonic'},
            {"op": DROP, "lane": 'turing1, arp', "seconds": 22, "say": 'pull the sequencers out of the patch'},
            {"op": SOLO, "lane": 'chorale', "seconds": 20, "say": 'the chorale alone'},
            {"op": CLEAR, "seconds": 26, "say": 'and the whole rack back'},
            {"op": ADD, "lane": 'turing1, arp', "seconds": 26, "say": 'the sequencers return, on different steps'},
            {"op": SET, "lane": 'turing1', "arg": 'mask', "value": '"<1 1 1 0 1 0 0 1>"', "seconds": 22, "say": 'rewrite the shift register'},
            {"op": DROP, "lane": 'bells, shimmer, echoes', "seconds": 26, "say": 'let the high voices go'},
            {"op": DROP, "lane": 'pings, boxes', "seconds": 22, "say": 'down to the bed'},
        ],
    },

    'acid': {
        "bpm": '~128', "cpm": '128/4',
        "blurb": '303 acid: squelching resonant bassline over a hard kick',
        "lanes": {
            'kick': 's("bd*4").gain(0.98).o(1)._scope().color("#f472b6")',
            'hats': 's("[~ hh]*4").gain(0.3).o(2).color("#94a3b8")',
            'ohat': 's("hh:3*8").gain(0.13).degradeBy(0.4).pan(rand).o(2)',
            'clap': 's("~ ~ cp ~").gain(0.4).room(0.3).o(2).color("#cbd5e1")',
            'acid': 'n("{0 0 12 0 3 0 7 10}%16").scale("a1:minor").s("sawtooth").o(3).color("#facc15")._pianoroll()',
            'sub': 'n("0*4").add(n("<0 -2>*2")).scale("a1:minor").s("sine").o(4).color("#fb7185")._scope()',
            'pad': 'n("<0,3,7 -2,2,5>*2").scale("a4:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("a4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.24).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick, four on the floor'},
            {"op": ADD, "lane": 'sub', "seconds": 16, "say": 'sub underneath'},
            {"op": FX, "lane": 'sub', "arg": '.attack(0.01).decay(0.4).sustain(0.3).release(0.2).lpf(150)', "seconds": 14, "say": 'keep it low'},
            {"op": FX, "lane": 'sub', "arg": '.duck("1").duckdepth(0.6)', "seconds": 14, "say": 'duck it'},
            {"op": ADD, "lane": 'acid', "seconds": 18, "say": 'the 303 line'},
            {"op": FX, "lane": 'acid', "arg": '.attack(0.004).decay(0.16).sustain(0.02).release(0.12)', "seconds": 14, "say": 'short and squelchy'},
            {"op": FX, "lane": 'acid', "arg": '.lpf(slider(0.25,0,1).range(200,3000)).lpq(10)', "seconds": 18, "say": 'tame it with an acid slider'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": FX, "lane": 'acid', "arg": '.delay(0.26).delaytime(0.1875).delayfeedback(0.45)', "seconds": 16, "say": 'delay for power'},
            {"op": SET, "lane": 'acid', "arg": 'lpq', "value": '15', "seconds": 16, "say": 'push the resonance'},
            {"op": ADD, "lane": 'clap', "seconds": 16, "say": 'clap'},
            {"op": FX, "lane": 'acid', "arg": '.distort(1.4)', "seconds": 18, "say": 'destroy it with distortion'},
            {"op": SET, "lane": 'acid', "arg": 'n', "value": '"{0 12 0 7 3 0 10 7}%16"', "seconds": 16, "say": 'rewrite the 303 line'},
            {"op": ADD, "lane": 'ohat', "seconds": 16, "say": 'open hats'},
            {"op": SOLO, "lane": 'acid', "seconds": 18, "say": 'isolate the acid'},
            {"op": CLEAR, "seconds": 16, "say": 'all back'},
            {"op": DROP, "lane": 'kick', "seconds": 18, "say": 'breakdown'},
            {"op": ADD, "lane": 'pad', "seconds": 18, "say": 'a pad in the gap'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand).attack(1.5).release(4).lpf(perlin.range(600,2000)).lpq(0).room(0.8)', "seconds": 16, "say": 'wide and slow'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick back'},
            {"op": SET, "lane": 'acid', "arg": 'lpq', "value": '8', "seconds": 16, "say": 'pull it back'},
            {"op": ADD, "lane": 'vox', "seconds": 18, "say": 'a voice in the machine'},
            {"op": DROP, "lane": 'ohat', "seconds": 18, "say": 'thin out'},
            {"op": DROP, "lane": 'vox', "seconds": 16, "say": 'and out'},
        ],
    },

    'psytrance': {
        "bpm": '~145', "cpm": '145/4',
        "blurb": 'rolling triplet bassline, hard kick, hypnotic leads',
        "lanes": {
            'kick': 's("bd*4").gain(1.0).o(1)._scope().color("#f472b6")',
            'roll': 'n("0*16").add(n("<0 -2>*2")).scale("e1:minor").s("sine").o(3)',
            'hats': 's("[~ hh]*8").gain(0.2).pan(rand).o(2).color("#94a3b8")',
            'ride': 's("hh:4*16").gain(0.1).degradeBy(0.5).o(2)',
            'lead': 'n("{0 3 7 10 7 3}%16").scale("e4:minor").s("supersaw").o(4).color("#facc15")._pianoroll()',
            'pad': 'n("<0,3,7 -2,2,5>*2").scale("e3:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
        },
        "script": [
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick, four on the floor'},
            {"op": ADD, "lane": 'roll', "seconds": 16, "say": 'the rolling bass'},
            {"op": FX, "lane": 'roll', "arg": '.struct("~ 1 1 ~ 1 1 ~ 1 1 ~ 1 1 ~ 1 1 ~")', "seconds": 16, "say": 'triplet feel'},
            {"op": FX, "lane": 'roll', "arg": '.attack(0.004).decay(0.09).sustain(0).release(0.06).lpf(280)', "seconds": 14, "say": 'tight and short'},
            {"op": FX, "lane": 'roll', "arg": '.duck("1").duckdepth(0.8).duckattack(0.06)', "seconds": 16, "say": 'duck hard against the kick'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": ADD, "lane": 'lead', "seconds": 18, "say": 'hypnotic lead'},
            {"op": FX, "lane": 'lead', "arg": '.detune(rand.range(0,0.3)).attack(0.005).decay(0.13).sustain(0.05).release(0.3)', "seconds": 14, "say": 'detune it'},
            {"op": FX, "lane": 'lead', "arg": '.lpf(slider(0.4,0,1).range(600,3600)).lpq(2).pan(rand)', "seconds": 18, "say": 'filter and swirl'},
            {"op": FX, "lane": 'lead', "arg": '.delay(0.35).delaytime(0.1875).delayfeedback(0.5)', "seconds": 16, "say": 'delay'},
            {"op": ADD, "lane": 'ride', "seconds": 16, "say": 'ride on top'},
            {"op": SOLO, "lane": 'lead', "seconds": 18, "say": 'isolate the lead'},
            {"op": CLEAR, "seconds": 16, "say": 'back in'},
            {"op": SET, "lane": 'lead', "arg": 'n', "value": '"{0 5 7 10 12 10 7 5}%16"', "seconds": 18, "say": 'new figure on the lead'},
            {"op": DROP, "lane": 'kick', "seconds": 18, "say": 'breakdown'},
            {"op": ADD, "lane": 'pad', "seconds": 18, "say": 'pad underneath'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand).attack(2).release(4).lpf(perlin.range(400,1600)).lpq(0).room(0.85)', "seconds": 16, "say": 'slow and wide'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick returns'},
            {"op": FX, "lane": 'lead', "arg": '.fm(0.4).fmwave("brown")', "seconds": 18, "say": 'FM it with noise'},
            {"op": DROP, "lane": 'ride', "seconds": 18, "say": 'thin'},
            {"op": DROP, "lane": 'lead', "seconds": 16, "say": 'out'},
        ],
    },

    'berlinschool': {
        "bpm": '~112', "cpm": '112/4',
        "blurb": 'Berlin School: two sequencers phasing under a travelling filter',
        # Klaus Schulze and Tangerine Dream ran *several* analog sequencers at
        # once and let them interact — the pattern construction is close to
        # Reich's phasing, and the rhythmic pulse is filled in by a tape echo
        # set to a division of the tempo rather than by more notes.
        "lanes": {
            # Mellotron choir and strings, not a low supersaw triad. The pad was
            # stacked triads at c2, which on a supersaw is mud under everything.
            'pad': 'n("<0,4,7 -3,0,4 -5,-1,2 0,4,7>").scale("c3:minor").s("gm_choir_aahs,gm_string_ensemble_1:0:0.5").attack(1.8).release(6).lpf(perlin.range(400,1500).slow(13)).lpq(0).gain(0.32).room(0.88).roomsize(8).o(1)._scope().color("#38bdf8")',
            'seq': 'n("{0 2 4 7 9 7 4 2}%16").scale("c3:minor").s("sawtooth").gain(0.45).o(2).color("#facc15")._pianoroll()',
            # The second sequencer. Same eight notes, twelve steps to the cycle
            # against the first one\'s sixteen, so the two drift in and out of
            # phase and never state the same pair twice.
            #
            # It was `.add(n(12))` before `.scale()`, and with a scale `n` is a
            # DEGREE, not a semitone: twelve degrees of C minor is Ab, so the
            # lane labelled "an octave up" was playing an Ab minor arpeggio over
            # a C minor sequence — a minor sixth out. Seven degrees is the octave.
            'octave': 'n("{0 2 4 7 9 7 4 2}%12").add(n(7)).scale("c3:minor").s("square").gain(0.2).o(3).color("#a78bfa")._pianoroll()',
            'kick': 's("bd*4").bank("RolandTR808").gain(0.5).o(4).color("#f472b6")',
        },
        "script": [
            {"op": ADD, "lane": 'pad', "seconds": 24, "say": 'mellotron choir, to begin'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand.range(0,0.15)).pan(sine.range(0.35,0.65).slow(17))', "seconds": 22, "say": 'let it drift'},
            {"op": ADD, "lane": 'seq', "seconds": 22, "say": 'the first sequencer'},
            # Fast attack, sharp decay, no sustain: the classic pluck.
            {"op": FX, "lane": 'seq', "arg": '.attack(0.005).decay(0.13).sustain(0).release(0.22)', "seconds": 20, "say": 'pluck it — no sustain at all'},
            {"op": FX, "lane": 'seq', "arg": '.lpf(slider(0.35,0,1).range(280,2800)).lpq(4).lpa(0.01).lpd(0.12).lpenv(3)', "seconds": 24, "say": 'and let the filter travel'},
            # The echo is what fills the pulse in this music, not more notes.
            {"op": FX, "lane": 'seq', "arg": '.delay(0.5).delaytime(0.375).delayfeedback(0.62).pan(sine.range(0.2,0.8).slow(9))', "seconds": 22, "say": 'tape echo fills the gaps'},
            {"op": ADD, "lane": 'octave', "seconds": 22, "say": 'a second sequencer, twelve steps against sixteen'},
            {"op": FX, "lane": 'octave', "arg": '.degradeBy(0.45).attack(0.005).decay(0.1).sustain(0).lpf(tri.range(700,3400).slow(7)).delay(0.35).delaytime(0.25)', "seconds": 20, "say": 'they phase against each other'},
            {"op": SET, "lane": 'seq', "arg": 'lpq', "value": '8', "seconds": 20, "say": 'more resonance'},
            {"op": ADD, "lane": 'kick', "seconds": 22, "say": 'a pulse underneath'},
            {"op": SET, "lane": 'seq', "arg": 'lpenv', "value": '6', "seconds": 20, "say": 'open the filter envelope right up'},
            {"op": SOLO, "lane": 'seq', "seconds": 20, "say": 'isolate the sequence'},
            {"op": CLEAR, "seconds": 20, "say": 'back'},
            {"op": SET, "lane": 'seq', "arg": 'n', "value": '"{0 3 7 9 7 3 0 -3}%16"', "seconds": 20, "say": 'rewrite the sequence — the whole point of the machine'},
            {"op": DROP, "lane": 'kick', "seconds": 22, "say": 'drop the pulse'},
            {"op": SET, "lane": 'seq', "arg": 'lpq', "value": '2', "seconds": 20, "say": 'soften the filter'},
            {"op": DROP, "lane": 'octave', "seconds": 22, "say": 'one sequencer again'},
            {"op": DROP, "lane": 'seq', "seconds": 20, "say": 'just the choir'},
        ],
    },

    'deephouse': {
        "bpm": '~120', "cpm": '120/4',
        "blurb": 'deep house: soft 808 kit, rhodes 9th chords, warm sub, brushed hats',
        "lanes": {
            'kick': 's("bd*4").bank("RolandTR808").gain(0.8).o(1)._scope().color("#f472b6")',
            'hats': 's("[~ hh]*4").bank("RolandTR808").gain(0.22).o(2).color("#94a3b8")',
            'shaker': 's("hh:2*8").bank("RolandTR808").gain(0.1).degradeBy(0.35).pan(rand).o(2).color("#94a3b8")',
            'rim': 's("~ rim").bank("RolandTR808").gain(0.3).room(0.35).o(2).color("#cbd5e1")',
            # Warm sub with a gentle filter envelope, not a bare sine.
            'bass': 'note("<f1 [f1 f1] c2 [d#2 c2]>*2").s("sine").lpf(420).lpa(0.03).lpd(0.2).lpenv(2).attack(0.02).decay(0.3).sustain(0.2).release(0.3).gain(0.8).o(3).color("#fb923c")._scope()',
            # Rhodes 9ths with proper voice leading — the deep-house chord.
            'rhodes': 'chord("<Fm9 Bbm9 Eb9 Abmaj7>").voicing().anchor("c5").struct("~ x ~ x").s("gm_epiano1").attack(0.02).release(1.4).lpf(1800).gain(0.5).room(0.5).o(4).color("#5eead4")._spectrum()',
            'pad': 'chord("<Fm9 Bbm9 Eb9 Abmaj7>").voicing().anchor("c4").s("triangle").attack(1.8).release(3).lpf(800).gain(0.22).room(0.7).o(5).color("#38bdf8")._spectrum()',
            'top': 'n("<12 14 12 17>*4").scale("f5:minor").s("triangle").gain(0.13).degradeBy(0.7).pan(rand).room(0.7).delay(0.45).o(6).color("#a78bfa")._pianoroll()',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("f4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.26).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'kick, hats, bass, rhodes', "seconds": 18, "say": 'soft kick, brushed hats, rhodes and sub together'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.6).duckattack(0.14)', "seconds": 15, "say": 'duck the sub gently'},
            {"op": ADD, "lane": 'rim', "seconds": 14, "say": 'rimshot on the two'},
            {"op": FX, "lane": 'rhodes', "arg": '.lpf(slider(0.45,0,1).range(700,2600)).lpq(0)', "seconds": 16, "say": 'open the rhodes up'},
            {"op": ADD, "lane": 'shaker', "seconds": 14, "say": 'shaker'},
            {"op": FX, "lane": 'hats', "arg": '.swingBy(1/3, 4)', "seconds": 15, "say": 'swing the hats'},
            {"op": ADD, "lane": 'pad', "seconds": 17, "say": 'a pad behind the chords'},
            {"op": FX, "lane": 'rhodes', "arg": '.off(0.125, x => x.gain(0.2).pan(0.3))', "seconds": 16, "say": 'echo the chords an eighth behind'},
            {"op": FX, "lane": 'rhodes', "arg": '.delay(0.28).delaytime(0.375).pan(sine.range(0.4,0.6).slow(9))', "seconds": 16, "say": 'delay and let it drift'},
            {"op": ADD, "lane": 'top', "seconds": 15, "say": 'something glinting on top'},
            {"op": SET, "lane": 'bass', "arg": 'lpenv', "value": '4', "seconds": 14, "say": 'a little more movement below'},
            {"op": DROP, "lane": 'kick, bass', "seconds": 16, "say": 'breakdown'},
            {"op": FX, "lane": 'pad', "arg": '.room(0.9).lpf(1500)', "seconds": 15, "say": 'let the pad flood it'},
            {"op": ADD, "lane": 'vox', "seconds": 15, "say": 'a voice in the space'},
            {"op": FX, "lane": 'vox', "arg": '.rev().delay(0.4).delaytime(0.5).room(0.5).pan(rand)', "seconds": 14, "say": 'reverse it'},
            {"op": ADD, "lane": 'kick, bass', "seconds": 18, "say": 'kick and sub return'},
            {"op": SOLO, "lane": 'rhodes', "seconds": 15, "say": 'just the rhodes'},
            {"op": CLEAR, "seconds": 17, "say": 'and back'},
            {"op": SET, "lane": 'rhodes', "arg": 'chord', "value": '"<Fm9 Db^7 Bbm9 C7>"', "seconds": 12, "say": 'turn the changes around'},
            {"op": SET, "lane": 'pad', "arg": 'chord', "value": '"<Fm9 Db^7 Bbm9 C7>"', "seconds": 16, "say": 'pad follows the change'},
            {"op": DROP, "lane": 'top, vox', "seconds": 15, "say": 'thin out'},
            {"op": DROP, "lane": 'shaker, rim', "seconds": 14, "say": 'out'},
        ],
    },

    'breakbeat': {
        "bpm": '~136', "cpm": '136/4',
        "blurb": 'chopped breaks, syncopated bass, rave stabs',
        "lanes": {
            'break': 's("bd ~ sd bd ~ bd sd ~").gain(0.85).o(1)._scope().color("#f472b6")',
            'hats': 's("hh*8").gain(0.2).degradeBy(0.25).pan(rand).o(2).color("#94a3b8")',
            'ghost': 's("sd:2*16").gain(0.08).degradeBy(0.75).o(2).color("#94a3b8")',
            'bass': 'n("<0 0 5 3 0 -2 5 7>*8").scale("c2:minor").s("sawtooth").o(3).color("#fb923c")._scope()',
            'stab': 'n("<0,3,7 -3,0,5>*4").scale("c4:minor").s("supersaw").o(4)',
            'pad': 'n("<0,3,7 -3,0,5>*2").scale("c3:minor").s("supersaw").o(5).color("#38bdf8")._spectrum()',
        },
        "script": [
            {"op": ADD, "lane": 'break', "seconds": 18, "say": 'the break'},
            {"op": ADD, "lane": 'bass', "seconds": 16, "say": 'syncopated bass'},
            {"op": FX, "lane": 'bass', "arg": '.attack(0.01).decay(0.22).sustain(0.1).release(0.2).lpf(slider(0.3,0,1).range(200,900)).lpq(3)', "seconds": 18, "say": 'filter it'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.5).duckattack(0.1)', "seconds": 16, "say": 'duck it'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": ADD, "lane": 'stab', "seconds": 18, "say": 'rave stabs'},
            {"op": FX, "lane": 'stab', "arg": '.degradeBy(0.55).detune(rand.range(0,0.3)).attack(0.01).decay(0.3).release(0.6)', "seconds": 16, "say": 'scatter them'},
            {"op": FX, "lane": 'stab', "arg": '.lpf(perlin.range(800,2600)).lpq(1).room(0.45).delay(0.3).delaytime(0.375)', "seconds": 18, "say": 'open and echo'},
            {"op": ADD, "lane": 'ghost', "seconds": 16, "say": 'ghost snares'},
            {"op": FX, "lane": 'break', "arg": '.fit()', "seconds": 16, "say": 'fit the break to the cycle'},
            {"op": SOLO, "lane": 'break', "seconds": 16, "say": 'isolate the break'},
            {"op": CLEAR, "seconds": 16, "say": 'back'},
            {"op": DROP, "lane": 'break', "seconds": 18, "say": 'breakdown'},
            {"op": ADD, "lane": 'pad', "seconds": 18, "say": 'a pad'},
            {"op": FX, "lane": 'pad', "arg": '.detune(rand).attack(1.5).release(3).lpf(perlin.range(400,1500)).lpq(0).room(0.8)', "seconds": 16, "say": 'wide'},
            {"op": ADD, "lane": 'break', "seconds": 18, "say": 'break returns'},
            {"op": SET, "lane": 'bass', "arg": 'n', "value": '"<0 0 3 5 0 -2 7 5>*8"', "seconds": 16, "say": 'rewrite the bassline'},
            {"op": SET, "lane": 'bass', "arg": 'lpq', "value": '7', "seconds": 16, "say": 'more bite'},
            {"op": DROP, "lane": 'ghost', "seconds": 18, "say": 'thin'},
            {"op": DROP, "lane": 'stab', "seconds": 16, "say": 'out'},
        ],
    },

    'dub': {
        "bpm": '~72', "cpm": '72/4',
        "blurb": 'deep bass, heavy delay throws, lots of space',
        "lanes": {
            'kick': 's("bd ~ ~ ~").gain(0.9).o(1)._scope().color("#f472b6")',
            'snare': 's("~ ~ sd ~").gain(0.38).o(2).color("#cbd5e1")',
            'hats': 's("[~ hh]*2").gain(0.14).o(2).color("#94a3b8")',
            'bass': 'n("<0 0 5 7>*4").scale("g1:minor").s("sine").o(3).color("#fb923c")._scope()',
            'chords': 'n("<0,3,7>*4").add(n("<0 0 5 7>*4")).scale("g3:minor").s("supersaw").o(4).color("#5eead4")._spectrum()',
            'echo': 'n("<12 10 7>*8").scale("g4:minor").s("triangle").o(5)',
        },
        "script": [
            {"op": ADD, "lane": 'bass', "seconds": 22, "say": 'deep bass first'},
            {"op": FX, "lane": 'bass', "arg": '.attack(0.02).decay(0.8).sustain(0.4).release(0.6).lpf(190)', "seconds": 18, "say": 'very low'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'kick'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.4)', "seconds": 16, "say": 'duck it'},
            {"op": ADD, "lane": 'snare', "seconds": 18, "say": 'snare'},
            {"op": FX, "lane": 'snare', "arg": '.room(0.85).delay(0.7).delaytime(0.5).delayfeedback(0.72)', "seconds": 20, "say": 'throw it into the delay'},
            {"op": ADD, "lane": 'chords', "seconds": 20, "say": 'chords'},
            {"op": FX, "lane": 'chords', "arg": '.degradeBy(0.6).detune(rand.range(0,0.25)).attack(0.02).decay(0.5).release(1.4)', "seconds": 18, "say": 'sparse'},
            {"op": FX, "lane": 'chords', "arg": '.lpf(slider(0.4,0,1).range(350,1300)).lpq(0).room(0.7).delay(0.6).delaytime(0.375).delayfeedback(0.65)', "seconds": 20, "say": 'filter and echo'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": ADD, "lane": 'echo', "seconds": 18, "say": 'something up high'},
            {"op": FX, "lane": 'echo', "arg": '.degradeBy(0.85).attack(0.01).release(2.5).pan(rand).room(0.9).delay(0.75).delaytime(0.75).delayfeedback(0.7)', "seconds": 20, "say": 'let it ring out'},
            {"op": SOLO, "lane": 'bass', "seconds": 18, "say": 'isolate the bass'},
            {"op": CLEAR, "seconds": 18, "say": 'back'},
            {"op": DROP, "lane": 'kick', "seconds": 20, "say": 'drop the kick'},
            {"op": DROP, "lane": 'snare', "seconds": 18, "say": 'dub it out'},
            {"op": ADD, "lane": 'kick', "seconds": 20, "say": 'kick returns'},
            {"op": SET, "lane": 'bass', "arg": 'n', "value": '"<0 0 3 5>*4"', "seconds": 18, "say": 'walk the bass somewhere new'},
            {"op": ADD, "lane": 'snare', "seconds": 18, "say": 'and the snare'},
            {"op": DROP, "lane": 'echo', "seconds": 18, "say": 'thin'},
            {"op": DROP, "lane": 'chords', "seconds": 16, "say": 'out'},
        ],
    },

    'lofi': {
        "bpm": '~80', "cpm": '80/4',
        "blurb": 'soft keys, brushed drums, warm and low-passed',
        "lanes": {
            'keys': 'n("<0,2,4 -3,-1,1 -5,-3,-1 <2,4,6 0,2,4>>*4").scale("eb3:major").s("triangle").o(1)._scope()',
            'bass': 'n("<0 -5 -7>*4").scale("eb2:major").s("sine").o(2).color("#fb923c")._scope()',
            'kick': 's("bd ~ ~ bd ~ ~ ~ ~").gain(0.62).o(3).color("#f472b6")',
            'snare': 's("~ ~ ~ ~ sd ~ ~ ~").gain(0.3).room(0.3).o(4).color("#cbd5e1")',
            'hats': 's("hh*8").gain(0.1).degradeBy(0.35).pan(rand).o(4).color("#94a3b8")',
            'twinkle': 'n("<7 9 12 14>*8").scale("eb5:major").s("triangle").o(5)',
        },
        "script": [
            {"op": ADD, "lane": 'keys', "seconds": 22, "say": 'soft keys'},
            {"op": FX, "lane": 'keys', "arg": '.attack(0.02).decay(0.7).sustain(0.25).release(1.6).lpf(1300).lpq(0)', "seconds": 18, "say": 'warm and dull'},
            {"op": ADD, "lane": 'bass', "seconds": 18, "say": 'bass'},
            {"op": FX, "lane": 'bass', "arg": '.attack(0.02).decay(0.6).sustain(0.3).release(0.5).lpf(250)', "seconds": 16, "say": 'round'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'a lazy kick'},
            {"op": ADD, "lane": 'snare', "seconds": 16, "say": 'snare'},
            {"op": FX, "lane": 'keys', "arg": '.room(0.6).delay(0.2).pan(sine.range(0.4,0.6).slow(7))', "seconds": 18, "say": 'space it'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'brushed hats'},
            {"op": ADD, "lane": 'twinkle', "seconds": 18, "say": 'something twinkling'},
            {"op": FX, "lane": 'twinkle', "arg": '.degradeBy(0.82).attack(0.01).release(2).pan(rand).room(0.8).delay(0.5)', "seconds": 18, "say": 'sparse'},
            {"op": SOLO, "lane": 'keys', "seconds": 18, "say": 'just the keys'},
            {"op": CLEAR, "seconds": 16, "say": 'back'},
            {"op": DROP, "lane": 'kick', "seconds": 18, "say": 'drop the drums'},
            {"op": DROP, "lane": 'snare', "seconds": 16, "say": 'let it float'},
            {"op": ADD, "lane": 'kick', "seconds": 18, "say": 'back in'},
            {"op": SET, "lane": 'keys', "arg": 'n', "value": '"<0,2,4 -1,1,3 -3,-1,1 <-5,-3,-1 2,4,6>>*4"', "seconds": 18, "say": 'change the chords under it'},
            {"op": FX, "lane": 'keys', "arg": '.lpf(slider(0.35,0,1).range(600,2200)).lpq(1)', "seconds": 18, "say": 'a slider on the keys'},
            {"op": SET, "lane": 'keys', "arg": 'lpq', "value": '4', "seconds": 16, "say": 'open them a little'},
            {"op": FX, "lane": 'bass', "arg": '.duck("3").duckdepth(0.35)', "seconds": 16, "say": 'duck the bass under the kick'},
            {"op": SET, "lane": 'bass', "arg": 'duckdepth', "value": '0.55', "seconds": 16, "say": 'a touch more pump'},
            {"op": ADD, "lane": 'snare', "seconds": 18, "say": 'and out'},
            {"op": DROP, "lane": 'twinkle', "seconds": 16, "say": 'thin'},
        ],
    },

    'synthwave': {
        "bpm": '~66', "cpm": '66/4',
        "blurb": 'cinematic synthwave: wide supersaw stacks, bells, long tails',
        "lanes": {
            'brass': 'n("<0,3,7,10 0,3,7,10 -2,2,5,9 <-4,0,3,7 -5,-1,2,7>>*4").scale("d3:minor").s("supersaw").o(1)._scope()',
            'low': 'n("<0 -5>*2").scale("d2:minor").s("supersaw").o(2).color("#fb7185")._scope()',
            'bells': 'n("<7 10 12 15>*4").scale("d5:minor").s("triangle").o(3).color("#a78bfa")._pianoroll()',
            'lead': 'n("<0 5 3 7>*8").scale("d4:minor").s("supersaw").o(4).color("#facc15")._pianoroll()',
        },
        "script": [
            {"op": ADD, "lane": 'brass', "seconds": 30, "say": 'a wide brass stack'},
            {"op": FX, "lane": 'brass', "arg": '.detune(rand.range(0,0.3)).attack(0.9).decay(2).sustain(0.6).release(5)', "seconds": 26, "say": 'slow attack, long tail'},
            {"op": FX, "lane": 'brass', "arg": '.lpf(slider(0.4,0,1).range(400,1900)).lpq(0).room(0.9).size(9)', "seconds": 26, "say": 'filter and a big room'},
            {"op": FX, "lane": 'brass', "arg": '.vib(0.6).vibmod(0.06).pan(sine.range(0.3,0.7).slow(23))', "seconds": 24, "say": 'vibrato, and let it drift'},
            {"op": ADD, "lane": 'low', "seconds": 26, "say": 'an octave below'},
            {"op": FX, "lane": 'low', "arg": '.detune(rand.range(0,0.15)).attack(2).release(7).lpf(280).lpq(0).room(0.75)', "seconds": 24, "say": 'deep'},
            {"op": ADD, "lane": 'bells', "seconds": 26, "say": 'bells above'},
            {"op": FX, "lane": 'bells', "arg": '.degradeBy(0.7).attack(0.01).decay(1).release(4).pan(rand).room(0.92).delay(0.5).delaytime(0.75).delayfeedback(0.5)', "seconds": 26, "say": 'scatter and echo'},
            {"op": ADD, "lane": 'lead', "seconds": 26, "say": 'a lead line'},
            {"op": FX, "lane": 'lead', "arg": '.degradeBy(0.78).detune(rand).attack(0.4).release(3.5).lpf(perlin.range(700,2400)).lpq(0).room(0.88)', "seconds": 24, "say": 'sparse and singing'},
            {"op": SOLO, "lane": 'lead', "seconds": 22, "say": 'isolate the lead'},
            {"op": CLEAR, "seconds": 22, "say": 'back'},
            {"op": DROP, "lane": 'brass', "seconds": 26, "say": 'drop the brass'},
            {"op": SET, "lane": 'lead', "arg": 'lpq', "value": '3', "seconds": 22, "say": 'a little edge'},
            {"op": ADD, "lane": 'brass', "seconds": 26, "say": 'and bring it back'},
            {"op": SET, "lane": 'lead', "arg": 'n', "value": '"<0 3 7 10 12 10 7 3>*8"', "seconds": 18, "say": 'take the lead somewhere else'},
            {"op": DROP, "lane": 'bells', "seconds": 24, "say": 'thinning'},
            {"op": DROP, "lane": 'lead', "seconds": 22, "say": 'quiet'},
        ],
    },

    'triphop': {
        "bpm": '~88', "cpm": '88/4',
        "blurb": 'slow heavy breaks, dusty keys, deep bass',
        "lanes": {
            'keys': 'n("<0,3,7 -2,2,5 -4,0,3 <0,3,7 -5,-1,2>>*4").scale("d4:minor").s("triangle").o(1)._scope()',
            'bass': 'n("<0 0 -3 -5>*4").scale("d2:minor").s("sine").o(2).color("#fb923c")._scope()',
            'drums': 's("bd ~ ~ sd ~ ~ bd ~").gain(0.8).o(3)',
            'hats': 's("[~ hh]*4").gain(0.14).degradeBy(0.3).o(4).color("#94a3b8")',
            'strings': 'n("<0,3,7 -2,2,5 -4,0,3 0,3,7>*2").scale("d5:minor").s("supersaw").o(5)',
            'vox': 'n("<0 ~ 3 ~ 5 ~ 3 ~>").scale("d4:minor").s("gm_voice_oohs,gm_choir_aahs:0:0.45").attack(0.7).release(3.5).clip(1.6).degradeBy(0.3).pan(perlin.slow(11)).gain(0.26).room(0.85).roomsize(6).delay(0.35).delaytime(0.375).delayfeedback(0.5).o(7).color("#e879f9")._spiral()',
        },
        "script": [
            {"op": ADD, "lane": 'keys', "seconds": 22, "say": 'dusty keys'},
            {"op": FX, "lane": 'keys', "arg": '.attack(0.02).decay(0.8).sustain(0.2).release(1.8).lpf(1200).lpq(0)', "seconds": 18, "say": 'warm'},
            {"op": ADD, "lane": 'bass', "seconds": 18, "say": 'deep bass'},
            {"op": FX, "lane": 'bass', "arg": '.attack(0.02).decay(0.7).sustain(0.35).release(0.5).lpf(220)', "seconds": 16, "say": 'heavy'},
            {"op": ADD, "lane": 'drums', "seconds": 18, "say": 'slow break'},
            {"op": FX, "lane": 'bass', "arg": '.duck("1").duckdepth(0.45)', "seconds": 16, "say": 'duck it'},
            {"op": FX, "lane": 'keys', "arg": '.room(0.7).delay(0.35).delaytime(0.5).pan(sine.range(0.4,0.6).slow(11))', "seconds": 18, "say": 'space'},
            {"op": ADD, "lane": 'hats', "seconds": 16, "say": 'hats'},
            {"op": ADD, "lane": 'strings', "seconds": 18, "say": 'strings underneath'},
            {"op": FX, "lane": 'strings', "arg": '.degradeBy(0.7).detune(rand.range(0,0.2)).attack(1.2).release(3).lpf(perlin.range(500,1600)).lpq(0).room(0.85)', "seconds": 18, "say": 'slow swell'},
            {"op": ADD, "lane": 'vox', "seconds": 18, "say": 'a vocal'},
            {"op": FX, "lane": 'vox', "arg": '.rev().delay(0.5).delaytime(0.375).room(0.6).pan(rand)', "seconds": 16, "say": 'reverse and throw it'},
            {"op": SOLO, "lane": 'keys', "seconds": 18, "say": 'isolate the keys'},
            {"op": CLEAR, "seconds": 16, "say": 'back'},
            {"op": DROP, "lane": 'drums', "seconds": 18, "say": 'drop the break'},
            {"op": ADD, "lane": 'drums', "seconds": 18, "say": 'and back in'},
            {"op": SET, "lane": 'keys', "arg": 'n', "value": '"<0,3,7 -5,-1,2 -2,2,5 <-4,0,3 0,3,7>>*4"', "seconds": 18, "say": 'move the changes around'},
            {"op": FX, "lane": 'keys', "arg": '.lpf(slider(0.4,0,1).range(500,2000)).lpq(1)', "seconds": 18, "say": 'a slider on the keys'},
            {"op": SET, "lane": 'keys', "arg": 'lpq', "value": '5', "seconds": 16, "say": 'dirty them up'},
            {"op": DROP, "lane": 'vox', "seconds": 18, "say": 'thin'},
            {"op": DROP, "lane": 'strings', "seconds": 16, "say": 'out'},
        ],
    },

}

DEFAULT_GENRE = "ambient"


def genre_names() -> list[str]:
    return sorted(GENRES)


def describe(genre: str) -> str:
    e = GENRES.get(genre)
    return f"{genre} ({e['bpm']}) — {e['blurb']}" if e else genre


def total_seconds(genre: str) -> float:
    e = GENRES.get(genre)
    return sum(m.get("seconds", 20) for m in e["script"]) if e else 0.0
