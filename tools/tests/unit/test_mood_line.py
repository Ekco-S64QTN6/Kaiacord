"""Her mood line says one thing per thing. Four signals were worded one each and
contradicted each other on 8 Nov: "neutral, energized, socially fresh,
fatigued/sleepy, very busy day"."""
import itertools

from utils.core.kaia_mood import mood_line


def test_the_night_it_contradicted_itself_now_reads_as_one_state():
    assert mood_line(0.0, 0.8, 0.8, 0.2, 20, 23) == \
        "[how you feel right now: even, wired but tired, a busy day of talking and still up for more]"


def test_no_combination_says_two_opposite_things():
    vals, aros, socs, circs, counts = (-0.6, 0, 0.3, 0.7), (0.2, 0.5, 0.8), (0.1, 0.3, 0.5, 0.8), (0.2, 0.4, 0.6, 0.9), (0, 10, 20)
    for v, a, e, c, n in itertools.product(vals, aros, socs, circs, counts):
        line = mood_line(v, a, e, c, n, 14)
        assert line.startswith("[how you feel right now: ") and line.endswith("]")
        energy = line[len("[how you feel right now: "):-1].split(", ")[1]
        assert not ("energized" in energy and "tired" in energy)     # one phrase for her energy
        assert not ("up for" in line and "talked out" in line)
        assert line.count("busy") <= 1 and "/" not in line


def test_the_state_line_is_in_her_terms():
    from utils.infrastructure.system import bot_state as bsm
    bs = bsm.BotState.__new__(bsm.BotState)
    bs.kaia_coherence, bs.kaia_dream_freshness, bs.kaia_engagement = 0.9, 0.9, 0.9
    assert bs.get_kaia_state_line() == "[in your head: thinking clearly, slept on things recently]"
    bs.kaia_coherence, bs.kaia_dream_freshness = 0.2, 0.1
    assert bs.get_kaia_state_line() == "[in your head: memory foggy, haven't slept on things in a while]"
