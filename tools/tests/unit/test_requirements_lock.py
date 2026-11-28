"""requirements.lock is the resolved graph CI and the deployment install."""
from packaging.requirements import Requirement

from tools.maintenance import lock_requirements as L


def test_the_lock_was_resolved_from_this_requirements_txt():
    assert L.recorded_hash() == L.requirements_hash(), (
        "requirements.txt changed without a new lock: "
        "venv/bin/python3 tools/maintenance/lock_requirements.py --write")


def test_every_direct_requirement_is_pinned_in_the_lock_within_its_range():
    pins = L.pins()
    wrong = []
    for line in L.REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        req = Requirement(line)
        version = pins.get(L._normal(req.name))
        if version is None or (req.specifier and version not in req.specifier):
            wrong.append(f"{req} -> {version}")
    assert not wrong, wrong


def test_a_stale_lock_is_refused(tmp_path, monkeypatch):
    lock = tmp_path / "requirements.lock"
    lock.write_text(L.HASH_PREFIX + "0" * 64 + "\naiohttp==3.14.4\n", encoding="utf-8")
    monkeypatch.setattr(L, "LOCK", lock)
    assert L.check() == 1
