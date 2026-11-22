"""The sky computations close the ephemeris they open."""
import pytest

from utils.sky import passes


class _Kernel:
    closed = False

    def close(self):
        self.closed = True


class _Load:
    def __init__(self):
        self.kernel = _Kernel()

    def __call__(self, name):
        assert name == "de421.bsp"
        return self.kernel


@pytest.mark.parametrize("compute, inner, args", [
    (passes._tonight, "_tonight_with", (passes.Observer(32.78, -96.80),)),
    (passes._passes, "_passes_with", ({}, passes.Observer(32.78, -96.80), 1.0)),
])
def test_the_ephemeris_is_closed_even_when_the_computation_fails(monkeypatch, compute, inner, args):
    """Left open, every !iss and !sky held the .bsp until garbage collection."""
    load = _Load()
    monkeypatch.setattr(passes, "_loader", lambda: load)

    def boom(*_a):
        raise RuntimeError("bad orbit")

    monkeypatch.setattr(passes, inner, boom)
    with pytest.raises(RuntimeError):
        compute(*args)
    assert load.kernel.closed
