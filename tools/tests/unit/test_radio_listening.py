"""Kaia listening: transcripts → EAMs, the schedule, receivers, the log, !radio."""
import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.radio import kiwi, phonetic, watch
from utils.radio import log as radio_log

# Real transcripts of eam.watch recordings (large-v3, band-passed), with the
# message eam.watch's listeners logged for the same broadcast.
IMPLICATE = ("This is Implicate, Implicate, break. 3, golf, papa, bravo, victor, 2, standby, 3, golf, papa, "
             "bravo, victor, 2, standby, 3, 3, golf, bravo, victor, 2, standby, message follows, 3, golf, bravo, "
             "victor, 2, kilo, 6, charlie, 4, yankee, 6, alpha, juliet, yankee, 3, Echo, Mike, Papaw, Papaw, 3, "
             "Alpha, Romeo, Hotel, Mike, Tango, Uniform, Mike, Alpha, Whiskey, I say again, three, golf, bravo, "
             "victor, two, kilo, six, charlie, four, yankee, six, alpha, Jalil Thank you Three Echo Mike Papa Papa "
             "Three Alpha Romeo Hotel Mike Tango Uniform Mike Alpha Whiskey This is Impiccate out")
TICK_TOCK = ("Charlie, Bravo, Yankee, Mike, Victor, Victor, stand by. Charlie, Bravo, Yankee, Mike, Victor, Victor, "
             "stand by. Charlie, Prado, Yankees, Mike, Victor, Victor, stand by, message follows. Charlie, Grotto, "
             "Dixie, Mike, Victor, Victor, Quebec, Chico, November, Oscar, Victor, Juliet, Kilo, Sierra, Foxtrot, 5, "
             "4, Uniform, Victor, 7, Zulu, 7, Echo, 6, Foxtrot, Romeo, Quebec, Aha, 3, 2, 5 a.m., Charlie, Bravo, "
             "Hanky, Mike, Victor, Victor, Kovac, Tango, November, Oscar, Victor, Julian, Kilo, Sierra, Foxtrot, 5, "
             "4, Uniform, Victor, 7, Zulu, 7, Echo, 6, Foxtrot, Romeo, Quebec, 3, 2, this is TikTok out.")


@pytest.mark.parametrize("transcript,truth,callsign,minimum", [
    (IMPLICATE, "3GPBV2K6C4Y6AJY3EMPP3ARHMTUMAW", "IMPLICATE", 1.0),
    (TICK_TOCK, "CBYMVVQTNOVJKSF54UV7Z7E6FRQP32", "TICK TOCK", 0.95),
])
def test_real_transcripts_decode_to_the_logged_message(transcript, truth, callsign, minimum):
    p = phonetic.parse(transcript, ["IMPLICATE", "TICK TOCK", "CUFF LINK"])
    assert p.callsign == callsign
    assert p.preamble == truth[:6]
    assert phonetic.accuracy(p.message, truth) >= minimum


def test_characters_outside_the_eam_alphabet_become_unknown():
    p = phonetic.parse("message follows alpha bravo eight charlie one delta echo foxtrot golf hotel "
                       "india juliett kilo lima mike november oscar papa quebec romeo")
    assert "8" not in p.message and "1" not in p.message and p.message.count("?") == 2


def test_disagreeing_readings_are_marked_not_guessed():
    assert phonetic.merge("ABCDE", "ABXDE") == "AB?DE"
    assert phonetic.merge("AB??E", "ABCDE") == "ABCDE"


def test_a_short_word_is_not_forced_onto_the_alphabet():
    assert phonetic.symbol("aha") is None and phonetic.symbol("Papaw") == "P"


DIRECTORY = """// header
var kiwisdr_com =
[
 {"status":"active","offline":"no","name":"A","sdr_hw":"KiwiSDR 2 ⏳🚫 Limits","bands":"0-30000000",
  "users":"1","users_max":"8","ext_api":"4","gps":"(38.9, -94.8)","snr":"30,33","loc":"Olathe, KS","url":"http://a.proxy.kiwisdr.com"},
 {"status":"active","offline":"no","name":"E","sdr_hw":"KiwiSDR 2","bands":"0-30000000",
  "users":"0","users_max":"8","ext_api":"0","gps":"(38.0, -97.0)","snr":"60,60","loc":"no API clients","url":"http://e.example:8073"},
 {"status":"active","offline":"no","name":"B","sdr_hw":"KiwiSDR 1 ⏳ Limits","bands":"0-30000000",
  "users":"0","users_max":"4","ext_api":"4","gps":"(39.0, -95.0)","snr":"40,40","loc":"limited","url":"http://b.example:8073"},
 {"status":"active","offline":"no","name":"C","sdr_hw":"KiwiSDR 2","bands":"0-30000000",
  "users":"8","users_max":"8","ext_api":"4","gps":"(40.0, -100.0)","snr":"45,45","loc":"full","url":"http://c.example:8073"},
 {"status":"active","offline":"no","name":"D","sdr_hw":"KiwiSDR 2","bands":"0-30000000",
  "users":"0","users_max":"8","ext_api":"4","gps":"(52.0, 5.0)","snr":"50,50","loc":"Netherlands","url":"http://d.example:8174"},
]
"""


def test_the_directory_skips_limited_full_and_api_closed_receivers():
    """ext_api 0: the receiver accepts a recorder, sends nothing, and closes it
    ten seconds later — silent !radio and empty recordings, all night."""
    rs = kiwi.parse_directory(DIRECTORY)
    assert {r.name for r in rs} == {"A", "C", "D"}          # B: time limit; E: no API clients
    na = kiwi.choose(rs, 8992, "na")
    assert [r.name for r in na] == ["A"]                   # C has no free slot
    assert na[0].port == 8073                              # proxies are listed without one
    assert [(r.name, r.port) for r in kiwi.choose(rs, 13470, "eu")] == [("D", 8174)]


def test_a_directory_in_the_wrong_shape_is_an_error():
    from utils.radio.fetch import FeedError
    with pytest.raises(FeedError):
        kiwi.parse_directory("<html>maintenance</html>")


def test_scheduled_jobs_fall_due_once():
    from utils.radio import priyom
    now = datetime(2026, 9, 24, 9, 12, tzinfo=timezone.utc)
    e11 = priyom.parse({"summary": "E11 8423kHz USB", "start": {"dateTime": "2026-09-24T09:13:00Z"}})
    s11 = priyom.parse({"summary": "S11a 8597kHz USB", "start": {"dateTime": "2026-09-24T09:13:00Z"}})
    jobs = watch.due_jobs(now, [e11, s11], done=set())
    kinds = {(j["kind"], j["station"]) for j in jobs}
    assert kinds == {("hfgcs", "HFGCS"), ("numbers", "E11")}    # 09:10 window; E11 is followed, S11a is not
    assert watch.due_jobs(now, [e11], done={j["key"] for j in jobs}) == []


def test_a_transcription_is_checked_against_eam_watch():
    from utils.radio import eam_watch
    radio_log.log_path().unlink(missing_ok=True)
    started = datetime(2026, 9, 1, 3, 35, tzinfo=timezone.utc)
    radio_log.add({"id": "t1", "kind": "hfgcs", "station": "HFGCS", "khz": 8992.0, "started": started.isoformat(),
                   "parsed": {"message": "CBYMVVQ?TNOVJKSF54UV7Z7E6FRQ?32"}, "check": None})
    human = eam_watch.parse({"id": "x", "type": "ALLSTATIONS", "sender": "TICK TOCK", "receiver": "CBYMVV",
                             "message": "CBYMVVQTNOVJKSF54UV7Z7E6FRQP32", "time": "2026-09-01 03:41:00"})
    unrelated = eam_watch.parse({"id": "y", "type": "ALLSTATIONS", "sender": "X", "receiver": "",
                                 "message": "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ", "time": "2026-09-01 03:40:00"})
    assert watch.cross_check([unrelated, human]) == 1
    check = radio_log.entries()[0]["check"]
    assert check["eam_id"] == "x" and check["accuracy"] >= 0.9
    assert watch.cross_check([human]) == 0                 # checked once
    radio_log.log_path().unlink(missing_ok=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_noise_and_non_eam_voice_are_dropped(tmp_path):
    def tone(seconds):
        p = tmp_path / f"t{seconds}.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"sine=frequency=800:duration={seconds}", "-ar", "12000", str(p)], check=True)
        return p
    rec = kiwi.Receiver("h", 8073, "n", "loc", 0, 0, 0, 8, 10, 0, 30_000_000)
    job = {"kind": "hfgcs", "station": "HFGCS", "khz": 8992.0, "mode": "usb"}
    now = datetime.now(timezone.utc)
    with patch.object(watch.transcribe, "available", return_value=True), \
         patch.object(watch.transcribe, "transcribe", AsyncMock(return_value="just someone talking about the weather")):
        assert asyncio.run(watch.process(job, tone(5), rec, now)) is None        # too short
        assert asyncio.run(watch.process(job, tone(40), rec, now)) is None       # not an EAM
    with patch.object(watch.transcribe, "available", return_value=True), \
         patch.object(watch.transcribe, "transcribe", AsyncMock(return_value=IMPLICATE)):
        entry = asyncio.run(watch.process(job, tone(40), rec, now))
    assert entry["parsed"]["preamble"] == "3GPBV2"
    assert (radio_log.clips_dir() / entry["clip"]).is_file()
    (radio_log.clips_dir() / entry["clip"]).unlink()
    radio_log.log_path().unlink(missing_ok=True)


def test_radio_history_is_kept_out_of_the_knowledge_base():
    assert "knowledge_base" not in str(radio_log.log_path())
    assert "knowledge_base" not in str(radio_log.clips_dir())


def _msg(content, in_voice=False):
    m = MagicMock()
    m.content = content
    m.channel.send = AsyncMock()
    m.guild.id = 1
    m.author.voice = MagicMock() if in_voice else None
    return m


def test_radio_status_and_live_refusals():
    from utils.commands import radio_handler as rh
    radio_log.log_path().unlink(missing_ok=True)
    m = _msg("!radio")
    asyncio.run(rh.handle_radio_command(MagicMock(), m))
    embed = m.channel.send.await_args.kwargs["embed"]
    assert "What Kaia has heard" in embed.title and "!nightshift" in embed.footer.text
    m = _msg("!radio hfgcs", in_voice=False)
    asyncio.run(rh.handle_radio_command(MagicMock(), m))
    assert "voice channel" in m.channel.send.await_args.kwargs["embed"].description


def test_no_radio_subprocess_writes_to_the_bots_terminal():
    """ffmpeg inherits fd 2 unless told otherwise — beneath the logging
    redirect — and its output broke the curses dashboard."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[3] / "utils" / "radio"
    live_src = (root / "live.py").read_text(encoding="utf-8")
    assert "stderr=subprocess.DEVNULL" in live_src
    for name in ("watch.py", "transcribe.py"):
        src = (root / name).read_text(encoding="utf-8")
        for call in src.split("subprocess.run(")[1:]:
            assert "capture_output=True" in call.split(")\n")[0] + call[:400], name


def test_a_recording_is_dated_by_its_own_file_not_the_watch():
    start = datetime(2026, 9, 24, 3, 10, tzinfo=timezone.utc)
    assert watch.heard_at(Path("20260924T031742Z_8992000_hfgcs_usb.wav"), start) == \
        datetime(2026, 9, 24, 3, 17, 42, tzinfo=timezone.utc)
    assert watch.heard_at(Path("odd.wav"), start) == start


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_without_a_transcript_an_hfgcs_opening_is_not_kept(tmp_path):
    p = tmp_path / "t.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=40",
                    "-ar", "12000", str(p)], check=True)
    rec = kiwi.Receiver("h", 8073, "n", "loc", 0, 0, 0, 8, 10, 0, 30_000_000)
    with patch.object(watch.transcribe, "available", return_value=False):
        assert asyncio.run(watch.process({"kind": "hfgcs", "station": "HFGCS", "khz": 8992.0, "mode": "usb"},
                                         p, rec, datetime.now(timezone.utc))) is None


def test_a_recorder_dies_with_the_process_that_started_it(tmp_path):
    """A recorder holds a slot on someone else's receiver. Orphaned by a crash
    or a killed script, two kept their slots for six hours."""
    import os, signal, subprocess, sys, textwrap, time
    script = tmp_path / "parent.py"
    script.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        sys.path.insert(0, {str(Path.cwd())!r})
        from utils.radio.kiwi import _die_with_parent
        p = subprocess.Popen(["sleep", "60"], preexec_fn=_die_with_parent)
        print(p.pid, flush=True)
        time.sleep(60)
    """))
    parent = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    parent.kill()
    parent.wait()
    for _ in range(20):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    os.kill(child, signal.SIGKILL)
    raise AssertionError("the recorder outlived its parent")


def test_every_recorder_spawn_dies_with_its_parent():
    src = Path("utils/radio/kiwi.py").read_text(encoding="utf-8")
    spawns = src.count("create_subprocess_exec(") + src.count("subprocess.Popen(")
    assert spawns and src.count("preexec_fn=_die_with_parent") == spawns
