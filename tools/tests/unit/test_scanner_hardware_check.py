"""The hardware check's own arithmetic, on synthetic spectra: no dongle here."""
import importlib.util
from datetime import datetime
from pathlib import Path

import numpy as np

import pytest

_PATH = Path(__file__).resolve().parents[3] / "tools" / "diagnostics" / "scanner_hardware_check.py"


@pytest.fixture(scope="module")
def check():
    """The tool as a module, loaded under a name that is not __main__ so its main() stays unrun."""
    spec = importlib.util.spec_from_file_location("scanner_hardware_check", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spectrum(check, carriers):
    """Flat noise with a 10 kHz-wide signal at each (frequency, dB over noise)."""
    freqs = check.SURVEY_CENTER_HZ + (np.arange(check.FINE_NFFT) - check.FINE_NFFT // 2) * (2_400_000 / check.FINE_NFFT)
    power = np.ones(check.FINE_NFFT)
    for f, db in carriers:
        power[np.abs(freqs - f) <= 5_000] += 10 ** (db / 10)
    return power, freqs


def test_watch_hours_window_and_midnight_wrap(check):
    at = lambda h, m=0: datetime(2026, 11, 14, h, m)
    assert check.in_watch_hours("00:00-06:00", at(3))
    assert not check.in_watch_hours("00:00-06:00", at(6))
    assert check.in_watch_hours("22:00-04:00", at(23)) and check.in_watch_hours("22:00-04:00", at(1))
    assert not check.in_watch_hours("22:00-04:00", at(12))
    assert not check.in_watch_hours("", at(3)) and not check.in_watch_hours("nonsense", at(3))


def test_a_carrier_is_found_and_an_empty_channel_is_not(check):
    power, freqs = _spectrum(check, [(162_550_000, 12)])
    levels = check.channel_levels(power, freqs, check.NWR_HZ)
    assert levels[162_550_000]["over_db"] >= check.PRESENT_DB
    assert abs(levels[162_550_000]["offset_hz"]) < 100
    assert levels[162_400_000]["over_db"] < 1 and levels[162_400_000]["offset_hz"] is None


def test_ppm_takes_the_sign_of_the_dongle_reading_high(check):
    # A dongle whose crystal runs 10 ppm fast shows 162.550 about 1.6 kHz high.
    power, freqs = _spectrum(check, [(162_550_000 + 1_626, 15)])
    levels = check.channel_levels(power, freqs, check.NWR_HZ)
    assert 9.0 <= check.ppm_from(levels) <= 11.0


def test_no_station_gives_no_ppm(check):
    power, freqs = _spectrum(check, [])
    assert check.ppm_from(check.channel_levels(power, freqs, check.NWR_HZ)) is None
