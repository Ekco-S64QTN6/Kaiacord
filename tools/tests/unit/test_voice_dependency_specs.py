"""The Discord voice stack must use the patched libsodium without [voice]'s stale cap."""
from importlib.util import find_spec
from pathlib import Path



def _requirements():
    return [
        line.strip() for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_discord_voice_requirements_do_not_reintroduce_vulnerable_pynacl_cap():
    requirements = _requirements()

    assert "discord.py==2.7.1" in requirements  # no [voice] extra
    assert "PyNaCl>=1.6.2" in requirements
    assert "davey>=0.1.6" in requirements
    assert not any(line.lower().startswith("discord.py[") for line in requirements)


def test_voice_crypto_packages_are_importable_without_the_discord_voice_extra():
    assert find_spec("discord") is not None
    assert find_spec("nacl") is not None
    assert find_spec("davey") is not None
