"""Clearing GPU memory must not load torch into a process that never used it."""
import subprocess
import sys


def test_clearing_does_not_import_torch():
    code = ("import sys\nfrom utils.infrastructure.gpu.clear_gpu_memory import clear_gpu_memory, force_clear_gpu\n"
            "clear_gpu_memory(silent=True); assert force_clear_gpu() is True\n"
            "assert 'torch' not in sys.modules, 'torch was imported'\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
