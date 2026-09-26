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
    w = wf.Watcher(on_catch=lambda c: None)
    center = 147_000_000
    d = FakeDongle(146_860_000, on_after_reads=wf.WARM_VISITS + 1)
    hit = None
    for _ in range(wf.WARM_VISITS + 4):
        hit = w._visit(d, center) or hit
    assert hit and abs(hit[0] - 146_860_000) <= 5000 and hit[1] > wf.GATE_DB


def test_a_constant_carrier_does_not_trigger():
    w = wf.Watcher(on_catch=lambda c: None)
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
