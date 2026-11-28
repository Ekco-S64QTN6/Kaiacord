#!/usr/bin/env python3
"""requirements.lock: every runtime package, transitive ones included, at the
version pip resolves requirements.txt to.

`requirements.txt` names direct dependencies, several with lower bounds only,
so the same commit installed a different graph on a later day. The lock is
installed as constraints (CI and deployment both):

    venv/bin/pip install -r requirements.txt -c requirements.lock

It is resolved for the interpreter that runs this tool (the bot's venv:
CPython 3.12, linux x86_64), and records a hash of requirements.txt, so an edit
to requirements.txt without a new lock fails `--check` (CI runs it).

    venv/bin/python3 tools/maintenance/lock_requirements.py            # --check
    venv/bin/python3 tools/maintenance/lock_requirements.py --write    # resolve (needs PyPI)

Review a new lock like a dependency change: `git diff requirements.lock`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
REQUIREMENTS = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock"
HASH_PREFIX = "# requirements.txt sha256: "


def requirements_hash(path: Path | None = None) -> str:
    return hashlib.sha256((path or REQUIREMENTS).read_bytes()).hexdigest()


def recorded_hash(lock: Path | None = None) -> str:
    lock = lock or LOCK
    try:
        for line in lock.read_text(encoding="utf-8").splitlines():
            if line.startswith(HASH_PREFIX):
                return line[len(HASH_PREFIX):].strip()
    except OSError:
        pass
    return ""


def pins(lock: Path | None = None) -> dict:
    """{normalised name: version} from a lock file."""
    lock = lock or LOCK
    out = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            out[_normal(name)] = version.strip()
    return out


def _normal(name: str) -> str:
    import re
    return re.sub(r"[-_.]+", "-", name).lower()


def resolve() -> list[tuple[str, str]]:
    """(name, version) for everything pip would install from requirements.txt."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
             "--disable-pip-version-check", "--report", str(report), "-r", str(REQUIREMENTS)],
            check=True,
        )
        data = json.loads(report.read_text(encoding="utf-8"))
    return sorted(((i["metadata"]["name"], i["metadata"]["version"]) for i in data["install"]),
                  key=lambda nv: _normal(nv[0]))


def write() -> int:
    resolved = resolve()
    pip_version = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True,
                                 text=True, check=True).stdout.split()[1]
    header = [
        f"# Resolved from requirements.txt for CPython {platform.python_version()} on "
        f"{sys.platform} {platform.machine()} (pip {pip_version}). Do not edit by hand.",
        HASH_PREFIX + requirements_hash(),
        "# Install: venv/bin/pip install -r requirements.txt -c requirements.lock",
        "# Regenerate after editing requirements.txt: venv/bin/python3 tools/maintenance/lock_requirements.py --write",
    ]
    LOCK.write_text("\n".join(header + [f"{name}=={version}" for name, version in resolved]) + "\n",
                    encoding="utf-8")
    print(f"requirements.lock: {len(resolved)} packages")
    return 0


def check() -> int:
    if not LOCK.exists():
        print("requirements.lock is missing: run lock_requirements.py --write", file=sys.stderr)
        return 1
    if recorded_hash() != requirements_hash():
        print("requirements.lock is stale: requirements.txt changed since it was resolved; "
              "run lock_requirements.py --write and commit both", file=sys.stderr)
        return 1
    print(f"requirements.lock matches requirements.txt ({len(pins())} packages)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="resolve requirements.txt and write the lock")
    args = ap.parse_args(argv)
    return write() if args.write else check()


if __name__ == "__main__":
    sys.exit(main())
