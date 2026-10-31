"""The booth and KAIA//RX cycle through every portrait of her.

"Any but the last" was random, not a rotation: t3, t2, t1, k59, t2 over five
booth launches, and Ekco heard it as the same portrait every time. Runs the real
kaia-codec.js under Node with a localStorage stand-in.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

CODEC = Path(__file__).resolve().parents[3] / "assets" / "kaia-avatar" / "js" / "kaia-codec.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node isn't installed")


def _launches(n: int, storage: dict | None = None) -> list:
    script = f"""
    const store = new Map(Object.entries({json.dumps(storage or {})}));
    globalThis.window = globalThis;
    globalThis.localStorage = {{ getItem: (k) => store.has(k) ? store.get(k) : null,
                                 setItem: (k, v) => store.set(k, String(v)) }};
    eval(require('fs').readFileSync({json.dumps(str(CODEC))}, 'utf8'));
    const out = [];
    for (let i = 0; i < {n}; i++) out.push(KaiaCodec.randomPortrait());
    console.log(JSON.stringify({{ out, all: KaiaCodec.PORTRAITS }}));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_every_portrait_is_shown_once_before_any_repeats():
    r = _launches(60)
    k = len(r["all"])
    for i in range(0, 60, k):
        assert sorted(r["out"][i:i + k]) == sorted(r["all"])


def test_never_the_same_portrait_twice_in_a_row():
    r = _launches(300)
    assert all(a != b for a, b in zip(r["out"], r["out"][1:]))


def test_a_stale_or_broken_bag_is_ignored():
    r = _launches(6, {"kaia-codec-portrait-bag": '["gone", 5]', "kaia-codec-portrait": "t1"})
    assert sorted(r["out"]) == sorted(r["all"]) and r["out"][0] != "t1"
