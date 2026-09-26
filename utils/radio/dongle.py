"""A minimal ctypes binding to librtlsdr: open, tune, read IQ, close.

pyrtlsdr 0.4/0.5 import `rtlsdr_set_dithering`, which the distribution's
librtlsdr 2.0.x does not export, and 0.3 needs the removed pkg_resources.
The waterfall needs eight calls, so it binds them directly: retuning in
process takes milliseconds, where a new `rtl_power`/`rtl_fm` process spends
about a second opening the device.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from typing import Optional

import numpy as np


def _lib():
    name = ctypes.util.find_library("rtlsdr") or "librtlsdr.so"
    lib = ctypes.CDLL(name)
    p = ctypes.c_void_p
    lib.rtlsdr_get_device_count.restype = ctypes.c_uint32
    lib.rtlsdr_open.argtypes = [ctypes.POINTER(p), ctypes.c_uint32]
    lib.rtlsdr_close.argtypes = [p]
    lib.rtlsdr_set_sample_rate.argtypes = [p, ctypes.c_uint32]
    lib.rtlsdr_set_center_freq.argtypes = [p, ctypes.c_uint32]
    lib.rtlsdr_set_tuner_gain_mode.argtypes = [p, ctypes.c_int]
    lib.rtlsdr_set_tuner_gain.argtypes = [p, ctypes.c_int]
    lib.rtlsdr_set_agc_mode.argtypes = [p, ctypes.c_int]
    lib.rtlsdr_reset_buffer.argtypes = [p]
    lib.rtlsdr_read_sync.argtypes = [p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    return lib


class Dongle:
    """One RTL-SDR, opened for the life of the object."""

    def __init__(self, index: int = 0, sample_rate: int = 2_400_000, gain_db: float = 40.0):
        self.lib = _lib()
        if self.lib.rtlsdr_get_device_count() < 1:
            raise RuntimeError("no RTL-SDR found")
        self.dev = ctypes.c_void_p()
        if self.lib.rtlsdr_open(ctypes.byref(self.dev), index) != 0:
            raise RuntimeError("the RTL-SDR is busy or could not be opened")
        self.sample_rate = sample_rate
        self.lib.rtlsdr_set_sample_rate(self.dev, sample_rate)
        self.lib.rtlsdr_set_agc_mode(self.dev, 0)
        self.lib.rtlsdr_set_tuner_gain_mode(self.dev, 1)          # manual
        self.lib.rtlsdr_set_tuner_gain(self.dev, int(gain_db * 10))
        self.lib.rtlsdr_reset_buffer(self.dev)
        self.center: Optional[int] = None

    def tune(self, freq_hz: int) -> bool:
        """Retune; False if the tuner refused twice. The R820T occasionally fails
        an I2C write on a fast retune ("r82xx_set_freq: failed=-9"), and a read
        after a failed retune is the previous frequency."""
        for _ in range(2):
            if self.lib.rtlsdr_set_center_freq(self.dev, int(freq_hz)) == 0:
                self.center = int(freq_hz)
                self.read(16384)             # discard the samples from mid-retune
                return True
        return False

    def read(self, n: int) -> np.ndarray:
        """n complex samples, scaled to about ±1."""
        n = int(n) * 2
        n -= n % 512                         # read_sync wants a multiple of 512 bytes
        buf = (ctypes.c_uint8 * n)()
        got = ctypes.c_int(0)
        if self.lib.rtlsdr_read_sync(self.dev, buf, n, ctypes.byref(got)) != 0:
            raise RuntimeError("RTL-SDR read failed")
        raw = np.frombuffer(buf, dtype=np.uint8, count=got.value).astype(np.float32)
        iq = (raw - 127.5) / 127.5
        return (iq[0::2] + 1j * iq[1::2]).astype(np.complex64)

    def close(self) -> None:
        if self.dev:
            self.lib.rtlsdr_close(self.dev)
            self.dev = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
