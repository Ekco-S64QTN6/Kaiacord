"""Where a record can be left: its outro and its last breakdown, from its own audio."""
import numpy as np
import pytest

from utils.audio import songmap as S
from utils.audio.beatgrid import Grid

BPM = 120.0
BAR = 240.0 / BPM                                  # 2 s


def _section(bars: int, *, kick: bool, lead: bool, rng,
             upper: bool = False, transients: bool = False) -> np.ndarray:
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
    if upper:
        mono += 0.18 * np.sin(2 * np.pi * 4200 * t)
    if transients:
        burst_len = int(0.025 * S.RATE)
        envelope = np.exp(-np.arange(burst_len) / (0.006 * S.RATE))
        for at in np.arange(0.25, bars * BAR, 0.5):
            i = int(round(at * S.RATE))
            if i + burst_len <= n:
                mono[i:i + burst_len] += 0.35 * rng.standard_normal(burst_len) * envelope
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




def test_audio_replacement_with_same_size_and_mtime_invalidates_memory_and_disk_maps(tmp_path, monkeypatch):
    from utils.audio.audio_identity import clear_audio_signature_cache

    monkeypatch.setattr(S, "MAP_DIR", tmp_path / "maps")
    S._MEM.clear()
    clear_audio_signature_cache()
    first_audio = _record((8, True, False), (40, True, True), (16, True, False))
    second_audio = _record((8, True, False), (56, True, True))
    decoded = []

    def decode(path):
        decoded.append(path)
        return first_audio if len(decoded) == 1 else second_audio

    monkeypatch.setattr(S, "_decode", decode)
    path = tmp_path / "same-path.mp3"
    path.write_bytes(b"A" * (3 * 1024 * 1024))
    first_stat = path.stat()

    first = S.get(str(path))
    assert first is not None and len(decoded) == 1

    # Clear only the memory cache: the second lookup must consume the disk map.
    S._MEM.clear()
    cached = S.get(str(path))
    assert cached is not None and len(decoded) == 1
    assert np.array_equal(first.lead, cached.lead)
    assert np.array_equal(first.upper, cached.upper)
    assert np.array_equal(first.transient, cached.transient)

    path.write_bytes(b"B" * (3 * 1024 * 1024))
    import os
    os.utime(path, ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns))
    replaced_stat = path.stat()
    assert replaced_stat.st_size == first_stat.st_size
    assert replaced_stat.st_mtime_ns == first_stat.st_mtime_ns

    # The warm memory entry and the on-disk NPZ both describe the old bytes.
    replaced = S.get(str(path))
    assert replaced is not None and len(decoded) == 2
    assert not np.array_equal(first.lead, replaced.lead)

    S._MEM.clear()
    from_disk = S.get(str(path))
    assert from_disk is not None and len(decoded) == 2
    assert np.array_equal(replaced.lead, from_disk.lead)
    S._MEM.clear()
    clear_audio_signature_cache()



def test_upper_band_and_spectral_flux_capture_distinct_activity():
    rng = np.random.default_rng(11)
    active = _section(8, kick=False, lead=False, rng=rng, upper=True, transients=True)
    quiet = _section(8, kick=False, lead=False, rng=rng)
    m = S.compute(np.concatenate((active, quiet), axis=0))
    assert m is not None
    assert m.db("upper", 0.0, 8 * BAR) > m.db("upper", 8 * BAR, 16 * BAR) + 4.0
    assert m.db("transient", 0.0, 8 * BAR) > m.db("transient", 8 * BAR, 16 * BAR) + 1.0


def test_phrase_profile_aligns_to_counted_bars_and_keeps_raw_time():
    m = S.compute(_record((8, True, False), (40, True, True), (16, True, False)))
    assert m is not None
    profile = S.profile_from_map(m, Grid(120.0, 2.0, 8.0, bar_known=True), phrase_bars=4)
    assert profile.aligned and profile.grid_bpm == 120.0
    assert profile.grid_contrast == 8.0
    assert profile.phrases[0].start == 0.0
    assert profile.phrases[0].end == pytest.approx(2.0)
    assert not profile.phrases[0].aligned and profile.phrases[0].bars is None
    assert profile.phrases[0].section == "intro_candidate"
    first_phrase = profile.phrases[1]
    assert first_phrase.start == pytest.approx(2.0)
    assert first_phrase.end == pytest.approx(10.0)
    assert first_phrase.aligned and first_phrase.bars == 4
    assert first_phrase.full_db > -2.0
    assert first_phrase.lead_db < -2.0  # the lead proxy remains a separate feature
    assert all(p.start < p.end for p in profile.phrases)


def test_profile_without_a_counted_bar_uses_unaligned_time_windows():
    m = S.compute(_record((8, True, False), (40, True, True), (16, True, False)))
    assert m is not None
    profile = S.profile_from_map(m, Grid(120.0, 0.5, 8.0, bar_known=False), fallback_window_s=7.0)
    assert not profile.aligned
    assert profile.grid_bpm is None and profile.grid_contrast is None
    assert profile.phrases
    assert all(not p.aligned and p.bars is None for p in profile.phrases)
    assert profile.phrases[0].start == 0.0
    assert profile.phrases[0].end == pytest.approx(7.0)


def test_phrase_profile_marks_breakdown_drop_and_outro_candidates():
    breakdown = _record((24, True, True), (8, False, True), (48, True, True),
                        (8, False, True), (16, True, True))
    m = S.compute(breakdown)
    assert m is not None
    profile = S.profile_from_map(m, Grid(120.0, 0.0, 8.0, bar_known=True))
    sections = [p.section for p in profile.phrases]
    assert "breakdown_candidate" in sections
    assert "drop_candidate" in sections

    outro_map = S.compute(_record((8, True, False), (40, True, True), (16, True, False)))
    assert outro_map is not None
    outro_profile = S.profile_from_map(outro_map, Grid(120.0, 0.0, 8.0, bar_known=True))
    assert "outro_candidate" in [p.section for p in outro_profile.phrases]


def test_phrase_profile_api_returns_fallback_without_claiming_grid_alignment(tmp_path, monkeypatch):
    from utils.audio import library

    m = S.compute(_record((8, True, False), (40, True, True), (16, True, False)))
    assert m is not None
    monkeypatch.setattr(library, "audio_signature", lambda *_args, **_kwargs: "stable-v2")
    monkeypatch.setattr(S, "get", lambda _path: m)
    profile = S.phrase_profile(str(tmp_path / "record.mp3"), None, fallback_window_s=9.0)
    assert profile is not None and not profile.aligned
    assert profile.phrases[0].bars is None
    assert profile.phrases[0].end == pytest.approx(9.0)


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
