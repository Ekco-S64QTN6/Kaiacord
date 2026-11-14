"""Where a record can be left: its outro and its last breakdown, from its own audio."""
import numpy as np
import pytest

from utils.audio import songmap as S

BPM = 120.0
BAR = 240.0 / BPM                                  # 2 s


def _section(bars: int, *, kick: bool, lead: bool, rng) -> np.ndarray:
    """Stereo audio: a 60 Hz kick on every beat, a sustained centred "voice"
    (a 660 Hz tone with a slow wobble), a little wide noise throughout."""
    n = int(bars * BAR * S.RATE)
    t = np.arange(n) / S.RATE
    left = 0.01 * rng.standard_normal(n)
    right = 0.01 * rng.standard_normal(n)
    mono = np.zeros(n)
    if kick:
        phase = (t % (60.0 / BPM))
        mono += 0.6 * np.sin(2 * np.pi * 60 * phase) * np.exp(-phase * 18)
    if lead:
        mono += 0.25 * np.sin(2 * np.pi * 660 * t + 2.0 * np.sin(2 * np.pi * 0.7 * t))
    return np.stack([left + mono, right + mono], axis=1).astype(np.float32)


def _record(*sections) -> np.ndarray:
    rng = np.random.default_rng(3)
    return np.concatenate([_section(b, kick=k, lead=v, rng=rng) for b, k, v in sections])


def test_the_outro_starts_where_what_was_up_front_stops():
    # 8 bars in, 40 of song, 16 of beat alone
    m = S.compute(_record((8, True, False), (40, True, True), (16, True, False)))
    end = 64 * BAR
    assert m.db("lead", 20 * BAR, 40 * BAR) > -2 and m.db("lead", 52 * BAR, 62 * BAR) < S.THIN_DB
    assert S.outro_start(m, end, BAR) == pytest.approx(48 * BAR, abs=BAR)


def test_a_record_that_ends_on_its_song_has_no_outro():
    m = S.compute(_record((8, True, False), (56, True, True)))
    assert S.outro_start(m, 64 * BAR, BAR) is None


def test_a_record_quiet_in_the_mids_for_most_of_its_length_has_no_outro():
    """The curve is against the record's own usual level: one loud passage and
    the rest reads as thin, which is no reason to leave it after a minute."""
    m = S.compute(_record((16, True, True), (64, True, False)))
    assert S.outro_start(m, 80 * BAR, BAR) is None


def test_the_last_breakdown_is_found_only_late_in_the_record():
    # song, an early breakdown, song, a late breakdown, the last drop
    audio = _record((24, True, True), (8, False, True), (48, True, True), (8, False, True), (16, True, True))
    m = S.compute(audio)
    length = 104 * BAR
    assert m.db("bass", 81 * BAR, 87 * BAR) < S.BREAK_DB < m.db("bass", 40 * BAR, 70 * BAR)
    assert S.last_break(m, length, BAR, length) == pytest.approx(80 * BAR, abs=BAR)
    # leaving at the early one would be leaving a third of the way in
    assert S.last_break(m, 60 * BAR, BAR, length) is None


def test_a_long_record_is_analysed_in_pieces_that_join_up():
    """An hour-long mix in one STFT is gigabytes: it is cut into chunks, and
    the curves must come out as if it were not."""
    audio = _record((8, True, False), (40, True, True), (16, True, False))
    whole = S.compute(audio)
    old = S._CHUNK_S
    try:
        S._CHUNK_S = 7.0
        pieces = S.compute(audio)
    finally:
        S._CHUNK_S = old
    assert len(whole.lead) == len(pieces.lead)
    k = int(60 * BAR / S.HOP_S)
    assert np.allclose(10 * np.log10(whole.lead[:k] + 1e-6), 10 * np.log10(pieces.lead[:k] + 1e-6), atol=1.5)


def test_the_map_is_cached_and_an_unreadable_file_has_none(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "MAP_DIR", tmp_path / "maps")
    S._MEM.clear()
    audio = _record((8, True, False), (40, True, True), (16, True, False))
    decodes = []
    monkeypatch.setattr(S, "_decode", lambda path: decodes.append(path) or audio)
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    first = S.get(str(f))
    S._MEM.clear()
    again = S.get(str(f))
    assert decodes == [str(f)] and np.allclose(first.lead, again.lead)
    assert S.get(str(tmp_path / "gone.mp3")) is None
    assert S.out_points(str(f), 64 * BAR, BPM, 64 * BAR)[0][0] == "outro"
    assert S.out_points(str(f), 64 * BAR, None, 64 * BAR) == []
