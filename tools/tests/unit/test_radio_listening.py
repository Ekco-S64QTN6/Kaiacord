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
    assert [(j["kind"], j["station"]) for j in jobs] == [
        ("hfgcs", "HFGCS"), ("numbers", "S11a"), ("numbers", "E11")]   # E11 last: mostly null messages
    assert watch.due_jobs(now, [e11], done={j["key"] for j in jobs}) == []


def _num(station, hhmm, khz=8000):
    from utils.radio import priyom
    return priyom.parse({"summary": f"{station} {khz}kHz USB", "start": {"dateTime": f"2026-09-24T{hhmm}:00Z"}})


def test_a_station_is_recorded_once_a_day():
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    done = {"num:E07:2026-09-24T08:00:8000"}
    assert watch.due_jobs(now, [_num("E07", "12:01")], done) == []
    assert watch.due_jobs(now, [_num("E07", "12:01")], {"num:E07:2026-09-23T08:00:8000"})


def test_the_day_stops_at_its_cap():
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    done = {f"num:X{i}:2026-09-24T0{i}:00:8000" for i in range(watch.NUMBERS_PER_DAY)}
    assert watch.due_jobs(now, [_num("E07", "12:01")], done) == []


def test_the_station_heard_longest_ago_goes_first():
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    done = {"num:E07:2026-09-23T08:00:8000", "num:V07:2026-09-20T08:00:8000"}
    jobs = watch.due_jobs(now, [_num("E07", "12:01"), _num("V07", "12:01", 9000)], done)
    assert [j["station"] for j in jobs if j["kind"] == "numbers"] == ["V07", "E07"]


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


def test_radio_answers_a_bad_request_with_the_usage():
    """`!radio station` read as a station called STATION; a mode or frequency
    no receiver has went straight to kiwirecorder."""
    from utils.commands import radio_handler as rh
    for text in ("!radio station", "!radio 7000 foo", "!radio 145000"):
        m = _msg(text, in_voice=True)
        with patch.object(rh.priyom, "refresh", AsyncMock(return_value={"items": []})), \
                patch("utils.radio.live.start", AsyncMock()) as start:
            asyncio.run(rh.handle_radio_command(MagicMock(), m))
        assert "!radio hfgcs" in m.channel.send.await_args.kwargs["embed"].description, text
        start.assert_not_awaited()


def test_no_free_receiver_is_said_not_logged_as_a_fault():
    from utils.commands import radio_handler as rh
    m = _msg("!radio hfgcs", in_voice=True)
    with patch("utils.radio.live.start", AsyncMock(side_effect=RuntimeError("no free receiver covers 8992 kHz right now"))), \
            patch("utils.audio.strudel_session.get_session", return_value=None):
        asyncio.run(rh.handle_radio_command(MagicMock(), m))
    assert "no free receiver" in m.channel.send.await_args.kwargs["embed"].description


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



@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_a_number_station_is_kept_as_a_recording_without_a_transcript(tmp_path):
    """Whisper looped on E11's digit groups — "8-1-4-0-8-0-0" forty times,
    "he was born on the hill". The catch is posted as a recording instead."""
    from utils.commands import radio_handler as rh
    p = tmp_path / "e11.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=40",
                    "-ar", "12000", str(p)], check=True)
    rec = kiwi.Receiver("h", 8073, "n", "loc", 0, 0, 0, 8, 10, 0, 30_000_000)
    job = {"kind": "numbers", "station": "E11", "khz": 9951.0, "mode": "usb"}
    with patch.object(watch.transcribe, "available", return_value=True), \
         patch.object(watch.transcribe, "transcribe", AsyncMock(return_value="8-1-4-0-8-0-0")) as tr:
        entry = asyncio.run(watch.process(job, p, rec, datetime.now(timezone.utc)))
    tr.assert_not_awaited()
    assert entry["transcript"] == "" and (radio_log.clips_dir() / entry["clip"]).is_file()
    assert "minutes of E11 — the clip is attached" in rh.entry_embed(entry).description
    assert "recorded" in rh._entry_line(1, entry)
    old = {**entry, "transcript": "Thank you. 8-1-4-0-8-0-0 8-1-4-0-8-0-0"}
    assert "8-1-4" not in rh._entry_line(1, old) and "8-1-4" not in rh.entry_embed(old).description
    (radio_log.clips_dir() / entry["clip"]).unlink()
    radio_log.log_path().unlink(missing_ok=True)

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


FAKE_RECORDER = '''
import sys, os
args = sys.argv[1:]
out = args[args.index("-d") + 1]
if "--crash" in open(os.path.join(os.path.dirname(__file__), "mode")).read():
    print("FileNotFoundError: no such directory", file=sys.stderr)
    sys.exit(0)
with open(os.path.join(out, "20260925T000000Z_8423000_e11_usb.wav"), "wb") as f:
    f.write(b"\\0" * 12000 * 2 * 5)
'''


def _fake_kiwiclient(tmp_path, monkeypatch, mode=""):
    from utils.radio import kiwi
    client = tmp_path / "kiwiclient"
    client.mkdir()
    (client / "kiwirecorder.py").write_text(FAKE_RECORDER)
    (client / "mode").write_text(mode)
    monkeypatch.setattr(kiwi, "KIWICLIENT", client)
    monkeypatch.setattr(kiwi, "RECORDER", client / "kiwirecorder.py")
    return kiwi.Receiver("rx.example", 8073, "rx", "", 0, 0, 0, 4, 20, 0, 30_000_000)


def test_a_recording_lands_in_a_relative_work_folder(tmp_path, monkeypatch):
    """The recorder runs in assets/kiwiclient/; memory/radio/work handed to it
    as-is pointed at a folder that doesn't exist, and every listen came back
    with 0 recordings."""
    import asyncio
    from utils.radio import kiwi
    r = _fake_kiwiclient(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    wavs = asyncio.run(kiwi.record(r, 8423, "usb", 5, Path("memory/radio/work"), label="e11"))
    assert [w.name for w in wavs] == ["20260925T000000Z_8423000_e11_usb.wav"]
    assert (tmp_path / "memory/radio/work" / wavs[0].name).is_file()


def test_a_recorder_that_quits_with_nothing_is_a_failure(tmp_path, monkeypatch):
    """kiwirecorder exits 0 when one of its threads crashes; that must reach the
    log and move on to the next receiver, not read as a quiet frequency."""
    import asyncio
    from utils.radio import kiwi
    from utils.radio.fetch import FeedError
    r = _fake_kiwiclient(tmp_path, monkeypatch, mode="--crash")
    with pytest.raises(FeedError, match="stopped early: FileNotFoundError"):
        asyncio.run(kiwi.record(r, 8423, "usb", 30, tmp_path / "work", label="e11"))


def test_uvb76_samples_fall_due_at_night_once():
    now = datetime(2026, 9, 26, 0, 2, tzinfo=timezone.utc)
    jobs = [j for j in watch.due_jobs(now, [], done=set()) if j["kind"] == "uvb76"]
    assert len(jobs) == 1 and jobs[0]["region"] == "ne" and jobs[0]["khz"] == 4625.0
    assert not [j for j in watch.due_jobs(now, [], done={jobs[0]["key"]}) if j["kind"] == "uvb76"]
    noon = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert not [j for j in watch.due_jobs(noon, [], done=set()) if j["kind"] == "uvb76"]
