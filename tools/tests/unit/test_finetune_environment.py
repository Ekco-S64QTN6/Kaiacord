"""The fine-tune toolchain is pinned, checked before a run and recorded after it."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"ft_{name}", ROOT / "finetune" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_package_the_pipeline_imports_is_pinned_exactly():
    hw = _load("02_check_hardware")
    pins = hw.pinned_versions()
    for name in ("unsloth", "unsloth_zoo", "torch", "transformers", "trl", "peft",
                 "datasets", "accelerate", "bitsandbytes"):
        assert pins.get(name), f"{name} is not pinned in finetune/requirements.txt"
    assert "git+" not in (ROOT / "finetune" / "requirements.txt").read_text()


def test_a_toolchain_that_differs_from_the_pins_is_reported():
    hw = _load("02_check_hardware")
    pins = {"trl": "0.24.0", "peft": "0.18.1", "torch": "2.10.0"}
    have = {"trl": "0.25.0", "peft": "0.18.1"}
    assert hw.version_mismatches(pins, have.get) == [
        "trl 0.25.0 (pinned 0.24.0)", "torch not installed (pinned 2.10.0)"]


def test_the_runtime_requirements_do_not_carry_the_gpu_toolchain():
    runtime = (ROOT / "requirements.txt").read_text().lower()
    for name in ("unsloth", "bitsandbytes", "trl==", "peft=="):
        assert name not in runtime
