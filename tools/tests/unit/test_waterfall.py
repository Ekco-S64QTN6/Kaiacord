"""The waterfall catches a transmission the moment it keys up, and the
demodulator recovers what was said."""
import numpy as np

from utils.radio import waterfall as wf


class FakeDongle:
    """Noise everywhere; an FM carrier with a 1 kHz tone at `freq` once `on`."""

    def __init__(self, freq, on_after_reads=0):
        self.freq, self.on_after, self.reads, self.center = freq, on_after_reads, 0, None
        self.rng = np.random.default_rng(1)
        self.t = 0

    def tune(self, f):
        self.center = f

    def read(self, n):
        self.reads += 1
        noise = (self.rng.normal(size=n) + 1j * self.rng.normal(size=n)).astype(np.complex64) * 0.05
        k = np.arange(self.t, self.t + n)
        self.t += n
        if self.reads > self.on_after and abs(self.freq - self.center) < wf.FS * 0.4:
            tone = np.sin(2 * np.pi * 1000 * k / wf.FS)
            phase = 2 * np.pi * (self.freq - self.center) * k / wf.FS + 2.5 * tone
            noise = noise + 0.5 * np.exp(1j * phase).astype(np.complex64)
        return noise


def test_a_carrier_keying_up_is_caught_on_the_right_channel():
    w = wf.Watcher(on_catch=lambda c: None, hops=([147_000_000], []))
    center = 147_000_000
    d = FakeDongle(146_860_000, on_after_reads=wf.WARM_VISITS + 1)
    hit = None
    for _ in range(wf.WARM_VISITS + 4):
        hit = w._visit(d, center) or hit
    assert hit and abs(hit[0] - 146_860_000) <= 5000 and hit[1] > wf.GATE_DB


def test_a_constant_carrier_does_not_trigger():
    w = wf.Watcher(on_catch=lambda c: None, hops=([147_000_000], []))
    d = FakeDongle(146_860_000, on_after_reads=0)          # on from the start
    assert not any(w._visit(d, 147_000_000) for _ in range(wf.WARM_VISITS + 6))


def test_the_demodulator_recovers_the_tone():
    d = FakeDongle(146_860_000)
    d.center = 147_000_000
    demod = wf.NbfmDemod(146_860_000 - 147_000_000)
    audio = np.concatenate([demod(d.read(wf.FS // 5)) for _ in range(5)]).astype(float)
    spec = np.abs(np.fft.rfft(audio[wf.AUDIO_FS // 5:]))
    peak = np.fft.rfftfreq(len(audio[wf.AUDIO_FS // 5:]), 1 / wf.AUDIO_FS)[np.argmax(spec[5:]) + 5]
    assert abs(peak - 1000) < 30


def test_cooldown_covers_the_channel_and_lengthens_for_a_constant_carrier(monkeypatch):
    w = wf.Watcher(on_catch=lambda c: None, hops=([147_000_000], []))
    center = 147_000_000
    d = FakeDongle(146_860_000, on_after_reads=wf.WARM_VISITS + 1)
    for _ in range(wf.WARM_VISITS + 3):
        w._visit(d, center)
    w.cooldown[146_857_500] = __import__("time").time() + 60      # a neighbouring 2.5 kHz step
    assert w._visit(d, center) is None
    monkeypatch.setattr(wf, "MAX_HOLD_S", 0.4)
    w.cooldown.clear()
    catch = w._hold(d, center, 146_860_000, 20.0)
    assert catch.seconds >= 0.4 and w.cooldown[146_860_000] - __import__("time").time() > 600


def test_a_carrier_that_keeps_coming_back_is_left_alone_longer(monkeypatch):
    """463.7125 ran the minute every time its half hour ran out."""
    import time as _time
    w = wf.Watcher(on_catch=lambda c: None, hops=([147_000_000], []))
    d = FakeDongle(146_860_000, on_after_reads=wf.WARM_VISITS + 1)
    for _ in range(wf.WARM_VISITS + 1):
        w._visit(d, 147_000_000)
    monkeypatch.setattr(wf, "MAX_HOLD_S", 0.4)
    waits = []
    for _ in range(5):
        w._hold(d, 147_000_000, 146_860_000, 20.0)
        waits.append(w.cooldown[146_860_000] - _time.time())
    assert [round(x / 60) for x in waits] == [30, 60, 120, 240, 240]


def test_the_hiss_reference_is_the_demodulators_level_on_an_empty_channel():
    """An FM discriminator reads phase, so noise at any input level comes out
    at one hiss level; carrier detection is measured against it."""
    rng = np.random.default_rng(0)
    for scale in (0.01, 1.0, 100.0):
        d = wf.NbfmDemod(100_000)
        iq = ((rng.standard_normal(480_000) + 1j * rng.standard_normal(480_000)) * scale).astype(np.complex64)
        audio = np.concatenate([d(np.roll(iq, 1000 * k)) for k in range(10)])        # 2 s
        on, _ = wf.carried(audio)
        hiss, _ = wf._frame_levels(audio)
        assert abs(np.median(hiss) - wf.HISS_DB) < 1.0 and on.mean() < 0.01


def test_voice_is_followed_only_under_a_full_quieting_carrier():
    """A weak signal fading in and out swings the voice band through the
    noise riding on it; followed, it held 469.044 for five minutes."""
    rng = np.random.default_rng(0)
    d = wf.NbfmDemod(100_000)
    iq = ((rng.standard_normal(480_000) + 1j * rng.standard_normal(480_000))).astype(np.complex64)
    hiss = np.concatenate([d(np.roll(iq, 1000 * k)) for k in range(20)]).astype(float)       # 4 s
    t = np.arange(len(hiss)) / wf.AUDIO_FS
    speech = np.sin(2 * np.pi * 800 * t) * (0.1 + np.abs(np.sin(2 * np.pi * 2.5 * t))) * 4000
    tail = hiss[: wf.AUDIO_FS]

    def over(quieting_db):
        body = hiss * 10 ** (-quieting_db / 20) + speech
        return np.clip(np.concatenate([body, tail]), -32767, 32767).astype(np.int16)

    assert wf.voice_like(over(14)) and not wf.voice_like(over(7))
    # A carrier fluttering in and out of quieting four times a second.
    flutter = np.where(np.sin(2 * np.pi * 2 * t) > 0, 10 ** (-14 / 20), 1.0)
    fluttering = np.clip(np.concatenate([hiss * flutter + speech, tail]), -32767, 32767).astype(np.int16)
    assert not wf.voice_like(fluttering)


def _carrier_then_hiss(on_s, off_s, times, quieting_db=20):
    """Demodulated audio: a carrier (hiss quieted) for on_s, hiss for off_s."""
    rng = np.random.default_rng(3)
    d = wf.NbfmDemod(100_000)
    iq = (rng.standard_normal(4_800_000) + 1j * rng.standard_normal(4_800_000)).astype(np.complex64)
    hiss = np.concatenate([d(iq[k:k + 480_000]) for k in range(0, 4_800_000, 480_000)]).astype(float)
    out, i = [], 0
    for _ in range(times):
        n_on, n_off = int(on_s * wf.AUDIO_FS), int(off_s * wf.AUDIO_FS)
        out.append(hiss[i:i + n_on] * 10 ** (-quieting_db / 20))
        out.append(hiss[i + n_on:i + n_on + n_off])
        i = (i + n_on + n_off) % (len(hiss) - n_on - n_off)
    return np.concatenate(out).astype(np.int16)


def test_the_squelch_stays_shut_on_pulses_and_opens_on_a_held_carrier():
    for audio, opens in ((_carrier_then_hiss(0.2, 1.3, 8), False), (_carrier_then_hiss(3.0, 1.0, 1), True)):
        sq = wf.Squelch()
        out = []
        for k in range(0, len(audio), wf.AUDIO_FS // 5):
            out += sq.push(audio[k:k + wf.AUDIO_FS // 5])
        out += sq.push(np.zeros(0, np.int16), final=True)
        assert sq.opened is opens and sum(len(o) for o in out) == len(audio) // wf.FRAME * wf.FRAME
        heard = np.concatenate(out)
        assert bool(heard[:wf.AUDIO_FS // 10].any()) is opens     # from the first syllable
