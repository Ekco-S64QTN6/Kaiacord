"""Run-together turns go back on their own lines, and nothing else moves."""
import importlib.util

import pytest


@pytest.fixture(scope="module")
def cul():
    spec = importlib.util.spec_from_file_location("_cul", "tools/maintenance/compact_user_logs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_an_empty_turn_followed_by_a_reply_is_split(cul):
    out, n = cul.split_flattened("[2026-09-15 15:06:10] Starkind: [2026-09-15 15:06:10] Kaia: it's a spiral.")
    assert n == 1 and out.splitlines()[-1] == "[2026-09-15 15:06:10] Kaia: it's a spiral."


def test_a_reply_appended_to_a_continuation_line_is_split(cul):
    cont = ("[2026-09-15 15:10:00] Starkind: first line of a long message\n"
            "resources are limited, classified [2026-09-15 15:11:14] Kaia: a tortoise. yes.")
    out, n = cul.split_flattened(cont)
    assert n == 1 and out.splitlines()[-1].startswith("[2026-09-15 15:11:14] Kaia:")
    assert out.replace("\n", " ").split() == cont.replace("\n", " ").split()      # no word changed


def test_a_pasted_log_excerpt_stays_where_it_is(cul):
    pasted = "[2026-09-15 15:10:00] Ekco: look at this old log\nit said [2026-03-01 10:00:00] Kaia: hello back then"
    assert cul.split_flattened(pasted)[1] == 0
