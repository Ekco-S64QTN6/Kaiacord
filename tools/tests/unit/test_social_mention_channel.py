"""A platform user's mentions keep one channel across restarts, so the
history bot_state saves is found again."""
import os
import subprocess
import sys

CODE = ("from utils.social.kaia_social_responder import mention_channel_id;"
        "print(mention_channel_id('bluesky', 'social_bluesky_someone.bsky.social'))")


def _in_process(seed):
    env = {**os.environ, "PYTHONHASHSEED": seed, "KAIACORD_LOG_FILE": os.devnull}
    return subprocess.run([sys.executable, "-c", CODE], env=env, capture_output=True,
                          text=True, check=True).stdout.strip().splitlines()[-1]


def test_the_channel_is_the_same_after_a_restart():
    assert _in_process("1") == _in_process("2")
