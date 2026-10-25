"""Kaia's own flock (utils/core/kaia_flock.py): children kept with their lineage,
votes that steer and cull, and the !art subcommands that reach them."""
import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.core import kaia_flock as kf
from utils.core import kaia_sheep as ks


def _genome(name, xforms=3):
    colors = "".join(f'<color index="{i}" rgb="{i} {255 - i} 200"/>' for i in range(256))
    xf = "".join(f'<xform weight="0.5" color="{k % 2}" {"spherical" if k % 2 else "swirl"}="1" '
                 f'coefs="0.6 {0.1 * k} {-0.1 * k} 0.6 {0.3 - 0.2 * k} 0.1"/>' for k in range(xforms))
    return (f'<flame name="{name}" size="200 200" center="0 0" scale="60" rotate="0" supersample="1" '
            f'quality="40" brightness="4" gamma="4" background="0 0 0">{xf}{colors}</flame>')


@pytest.fixture
def flocks(tmp_path, monkeypatch):
    """An Electric Sheep flock of three and an empty one of hers, both on disk."""
    monkeypatch.setattr(ks, "FLOCK_DIR", tmp_path / "flock")
    monkeypatch.setattr(ks, "INDEX", tmp_path / "flock" / "index.json")
    monkeypatch.setattr(kf, "FLOCK", tmp_path / "kaia_flock")
    monkeypatch.setattr(kf, "INDEX", tmp_path / "kaia_flock" / "index.json")
    monkeypatch.setattr(kf, "VOTES", tmp_path / "votes.json")
    ks.FLOCK_DIR.mkdir()
    index = {}
    for n in ("00541", "00576", "01039"):
        ks.add_genomes(_genome(f"electricsheep.248.{n}"), index)
    ks.save_index(index)
    return tmp_path


def test_a_child_joins_her_flock_with_its_lineage(flocks):
    a = kf.adopt(_genome("x"), ["electricsheep.248.00541", "electricsheep.248.00576"], "bred")
    b = kf.adopt(_genome("y"), [a], "mutated")
    assert (a, b) == ("kaia.1", "kaia.2")
    assert 'name="kaia.2"' in kf.genome_of(b)                    # renamed in the genome itself
    assert kf.depth(a) == 1 and kf.depth(b) == 2
    assert kf.ancestors(b) == ["electricsheep.248.00541", "electricsheep.248.00576"]
    credit = kf.credit([b])
    assert "mutated from kaia.1" in credit and "electricsheep.248.00541" in credit   # the licence's sheep numbers
    assert ks.CREDIT in credit


def test_sheep_are_named_the_way_people_type_them(flocks):
    kf.adopt(_genome("x"), ["electricsheep.248.00541"], "mutated")
    assert kf.resolve("k1") == kf.resolve("kaia.1") == "kaia.1"
    assert kf.resolve("541") == kf.resolve("00541") == "electricsheep.248.00541"
    assert kf.resolve("electricsheep.248.01039") == "electricsheep.248.01039"
    assert kf.resolve("k9") is None and kf.resolve("999") is None
    kf.record_post(10, 5, ["kaia.1"])
    assert kf.resolve("last", 5) == "kaia.1" and kf.resolve("last", 6) is None


def test_a_vote_is_one_per_person_and_can_change_or_be_taken_back(flocks):
    kf.record_post(10, 5, ["electricsheep.248.00541"])
    assert kf.vote(10, 1, kf.UP, True) == [("electricsheep.248.00541", 1)]
    assert kf.vote(10, 1, kf.UP, True) == [("electricsheep.248.00541", 1)]        # not twice
    assert kf.vote(10, 1, kf.DOWN, True) == [("electricsheep.248.00541", -1)]     # changed their mind
    assert kf.vote(10, 1, kf.DOWN, False) == [("electricsheep.248.00541", 0)]     # took it back
    assert kf.vote(10, 1, "🔥", True) == [] and kf.vote(11, 1, kf.UP, True) == []  # not a vote / not a sheep


def test_a_morph_vote_counts_for_both_ends(flocks):
    kf.record_post(10, 5, ["electricsheep.248.00541", "electricsheep.248.00576"])
    assert [s for _, s in kf.vote(10, 1, kf.UP, True)] == [1, 1]


def test_votes_steer_the_pick_and_a_culled_sheep_is_never_used(flocks):
    kf.record_post(10, 5, ["electricsheep.248.00541"])
    kf.record_post(11, 5, ["electricsheep.248.00576"])
    for user in (1, 2, 3):
        kf.vote(10, user, kf.UP, True)
    for user in (1, 2):
        kf.vote(11, user, kf.DOWN, True)
    assert "electricsheep.248.00576" not in kf.gene_pool()
    picks = [kf.pick(random.Random(s)) for s in range(300)]
    assert "electricsheep.248.00576" not in picks
    assert picks.count("electricsheep.248.00541") > picks.count("electricsheep.248.01039")
    picked = {ks.choose(random.Random(s), None, breed_chance=0).parents[0] for s in range(60)}
    assert "electricsheep.248.00576" not in picked                # !art's own pick obeys the cull


def test_her_own_sheep_are_in_the_gene_pool(flocks):
    kf.adopt(_genome("x"), ["electricsheep.248.00541"], "mutated")
    assert "kaia.1" in kf.gene_pool()


def test_art_subcommands_parse_with_names_before_the_prompt():
    from utils.commands.art_handler import parse_args
    o = parse_args("!art breed 541 k3 a red storm")
    assert (o["action"], o["names"], o["prompt"]) == ("breed", ["541", "k3"], "a red storm")
    o = parse_args("!art sheep last loop")
    assert (o["action"], o["names"], o["loop"]) == ("sheep", ["last"], True)
    assert parse_args("!art loop breed")["loop"] is True
    assert parse_args("!art morph k2 k5")["action"] == "morph"
    o = parse_args("!art a 541 dream")                               # a number in a prompt is words
    assert (o["action"], o["names"], o["prompt"]) == ("pick", [], "a 541 dream")


def test_the_vote_listener_ignores_her_own_reactions(flocks):
    from utils.commands.art_handler import install_vote_listener
    listeners = {}
    bot = SimpleNamespace(user=SimpleNamespace(id=99), add_listener=lambda fn, name: listeners.__setitem__(name, fn))
    install_vote_listener(bot)
    kf.record_post(10, 5, ["electricsheep.248.00541"])
    vote = lambda uid, emoji="👍": SimpleNamespace(user_id=uid, message_id=10, emoji=emoji)
    asyncio.run(listeners["on_raw_reaction_add"](vote(99)))        # the button she put there
    assert kf.score("electricsheep.248.00541") == 0
    asyncio.run(listeners["on_raw_reaction_add"](vote(1)))
    assert kf.score("electricsheep.248.00541") == 1
    asyncio.run(listeners["on_raw_reaction_remove"](vote(1)))
    assert kf.score("electricsheep.248.00541") == 0


def test_an_unknown_sheep_is_said_so_not_drawn(flocks, monkeypatch):
    from utils.commands import art_handler
    monkeypatch.setattr(art_handler, "_sheep_ready", lambda: True)
    monkeypatch.setattr(art_handler, "_last_art_time", {})
    channel = SimpleNamespace(id=5, send=AsyncMock())
    msg = SimpleNamespace(content="!art breed k7 541", channel=channel, attachments=[], author=None)
    asyncio.run(art_handler.handle_art_command(SimpleNamespace(), msg, None))
    assert "k7" in channel.send.await_args.kwargs["embed"].description
    assert channel.send.await_count == 1


def test_the_flock_listing_shows_hers_and_the_loved(flocks):
    from utils.commands.art_handler import flock_embed
    kf.adopt(_genome("x"), ["electricsheep.248.00541", "electricsheep.248.00576"], "bred")
    kf.record_post(10, 5, ["kaia.1"])
    kf.vote(10, 1, kf.UP, True)
    embed = flock_embed()
    text = embed.description + "".join(f.value for f in embed.fields)
    assert "1 of her own" in embed.description and "3 electric sheep" in embed.description
    assert "`kaia.1` +1 · bred from electricsheep.248.00541 × electricsheep.248.00576" in text


@pytest.mark.skipif(not ks.flam3_bin("flam3-genome"), reason="flam3 is not installed here")
def test_real_breeding_mutation_and_a_morph(flocks, monkeypatch):
    monkeypatch.setattr(ks, "_preview_ok", lambda genome, strict=False: True)   # the toy sheep are plain
    rng = random.Random(3)
    child = kf.breed(rng, "electricsheep.248.00541", "electricsheep.248.00576")
    assert child and child.parents == ["electricsheep.248.00541", "electricsheep.248.00576"]
    assert child.genome.count("<xform") >= 1
    mutant = kf.mutate(rng, "electricsheep.248.01039")
    assert mutant and mutant.method == "mutated" and mutant.genome != kf.genome_of("electricsheep.248.01039")
    out = flocks / "m.mp4"
    image, info = ks.render_transition(kf.genome_of("electricsheep.248.00541"), child.genome, out,
                                       width=64, frames=6, quality=10)
    assert out.stat().st_size > 0 and info["frames"] == 7 and image.size[0] == 64


def test_reading_the_help_or_the_flock_does_not_start_the_cooldown(flocks, monkeypatch):
    from utils.commands import art_handler
    monkeypatch.setattr(art_handler, "_last_art_time", {})
    monkeypatch.setattr(art_handler, "_sheep_ready", lambda: True)
    channel = SimpleNamespace(id=5, send=AsyncMock())
    say = lambda text: SimpleNamespace(content=text, channel=channel, attachments=[], author=None)
    asyncio.run(art_handler.handle_art_command(SimpleNamespace(), say("!art help"), None))
    asyncio.run(art_handler.handle_art_command(SimpleNamespace(), say("!art flock"), None))
    asyncio.run(art_handler.handle_art_command(SimpleNamespace(), say("!art breed k9"), None))
    replies = [c.kwargs["embed"].description or "" for c in channel.send.await_args_list]
    assert not any("cooling down" in r for r in replies)
    assert "k9" in replies[-1]                                     # it got as far as reading the names
