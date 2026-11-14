"""The DJ booth and the records start."""

import pytest


def test_waveform_reads_the_decode_as_a_stream(tmp_path):
    import shutil
    import wave
    import numpy as np
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    from utils.audio import dj_dashboard
    rate, seconds = 8000, 12
    t = np.arange(rate * seconds) / rate
    tone = (np.sin(2 * np.pi * 100 * t) * 12000).astype(np.int16)
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(tone.tobytes())
    got = dj_dashboard.waveform(str(path))
    assert got is not None
    assert abs(got["seconds"] - seconds) < 0.6

    # The same numbers the whole-buffer computation gave.
    import base64
    import subprocess
    graph = ("[0:a]aresample=8000,pan=mono|c0=0.5*c0+0.5*c1,asplit=3[a][b][c];"
             "[a]lowpass=f=180,lowpass=f=180[l];[b]highpass=f=180,lowpass=f=2500[m];"
             "[c]highpass=f=2500[h];[l][m][h]amerge=inputs=3[out]")
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-filter_complex", graph,
                          "-map", "[out]", "-f", "s16le", "-ar", str(dj_dashboard.WAVE_RATE), "-ac", "3", "pipe:1"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16)
    step = dj_dashboard.WAVE_RATE // dj_dashboard.WAVE_COLS_PER_S
    cols = len(x) // (3 * step)
    x = x[: cols * step * 3].reshape(cols, step, 3).astype(np.float32)
    out = np.sqrt(np.mean(x * x, axis=1))
    scale = np.percentile(out, 99.5, axis=0)
    scale[scale == 0] = 1.0
    want = np.clip(out / scale * 255.0, 0, 255).astype(np.uint8)
    have = np.frombuffer(base64.b64decode(got["data"]), dtype=np.uint8).reshape(-1, 3)
    assert have.shape == want.shape and (have == want).all()
