"""The UV-K5 cable tool against a simulated radio on a pseudo-terminal.

The tool opens the pty's far end exactly as it would /dev/ttyUSB0, so framing,
obfuscation, timeouts and the backup's double read are exercised over a real
tty. What the simulation cannot prove is that a real radio speaks this
dialect; that is checked the first time the radio is plugged in (`info`).
"""
import importlib.util
import json
import os
import select
import struct
import threading
from pathlib import Path

import pytest

uvk5 = None


@pytest.fixture(autouse=True)
def _tool():
    """Load the tool under its own name (never __main__), once, at test time."""
    global uvk5
    if uvk5 is None:
        spec = importlib.util.spec_from_file_location(
            "uvk5", Path(__file__).resolve().parents[2] / "maintenance" / "uvk5.py")
        uvk5 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(uvk5)


class FakeRadio(threading.Thread):
    """Answers hello and EEPROM reads the way the radio does, or repeats the
    bootloader beacon unasked."""

    def __init__(self, mode="normal", firmware=b"k5_2.01.26", boot_version=b"2.00.06", flip_on_pass=None):
        super().__init__(daemon=True)
        self.master, slave = os.openpty()
        self.path = os.ttyname(slave)
        self.slave = slave
        self.mode, self.firmware, self.boot_version = mode, firmware, boot_version
        self.eeprom = bytearray((i * 7) & 0xFF for i in range(uvk5.EEPROM_SIZE))
        self.flip_on_pass = flip_on_pass       # corrupt one byte on this read pass (a loose plug)
        self.reads_at_zero = 0
        self.stop = threading.Event()
        self.heard = []

    def send(self, cmd, body):
        os.write(self.master, uvk5.frame(uvk5.message(cmd, body)))

    def run(self):
        buf = b""
        while not self.stop.is_set():
            if self.mode == "bootloader":
                self.send(uvk5.BOOT_BEACON, b"\x11" * 16 + self.boot_version.ljust(16, b"\x00"))
            r, _, _ = select.select([self.master], [], [], 0.05)
            if not r:
                continue
            try:
                buf += os.read(self.master, 4096)
            except OSError:
                return
            while True:
                start = buf.find(b"\xab\xcd")
                if start < 0 or len(buf) < start + 4:
                    break
                n = struct.unpack("<H", buf[start + 2:start + 4])[0]
                if len(buf) < start + 4 + n + 4:
                    break
                raw, buf = buf[start:start + 8 + n], buf[start + 8 + n:]
                body = uvk5.xor(raw[4:4 + n + 2])
                payload, crc = body[:n], struct.unpack("<H", body[n:n + 2])[0]
                assert crc == uvk5.crc16_xmodem(payload), "tool sent a bad CRC"
                cmd = struct.unpack("<H", payload[:2])[0]
                self.heard.append(cmd)
                if self.mode != "normal":
                    continue
                if cmd == uvk5.HELLO:
                    self.send(uvk5.HELLO_REPLY, self.firmware.ljust(16, b"\x00") + b"\x00" * 20)
                elif cmd == uvk5.READ:
                    off, size = struct.unpack("<HB", payload[4:7])
                    data = bytearray(self.eeprom[off:off + size])
                    if off == 0:
                        self.reads_at_zero += 1
                    if self.flip_on_pass == self.reads_at_zero and off == 0x0400:
                        data[3] ^= 0xFF
                    self.send(uvk5.READ_REPLY, struct.pack("<HBB", off, size, 0) + bytes(data))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.join(1)
        os.close(self.master)
        os.close(self.slave)


def test_crc_is_xmodem():
    assert uvk5.crc16_xmodem(b"123456789") == 0x31C3        # the standard check value


def test_a_frame_carries_its_payload_obfuscated():
    f = uvk5.frame(b"\x14\x05\x04\x00" + uvk5.SESSION)
    assert f[:2] == b"\xab\xcd" and f[-2:] == b"\xdc\xba" and f[2:4] == b"\x08\x00"
    assert uvk5.xor(f[4:12]) == b"\x14\x05\x04\x00" + uvk5.SESSION
    assert f[4:12] != b"\x14\x05\x04\x00" + uvk5.SESSION


def test_info_reads_the_firmware_version():
    with FakeRadio() as radio:
        port = uvk5.Port(radio.path)
        try:
            assert uvk5.hello(port) == "k5_2.01.26"
        finally:
            port.close()


def test_backup_reads_everything_twice_and_keeps_the_calibration(tmp_path):
    with FakeRadio() as radio:
        port = uvk5.Port(radio.path)
        try:
            path = uvk5.backup(port, tmp_path)
        finally:
            port.close()
        assert path.read_bytes() == bytes(radio.eeprom) and radio.reads_at_zero == 2
    meta = json.loads(path.with_suffix(".json").read_text())
    assert meta["bytes"] == 0x2000 and meta["calibration"]["range"] == "0x1E00-0x1FFF"
    assert not meta["calibration"]["blank"] and meta["firmware"] == "k5_2.01.26"
    assert uvk5.READ in radio.heard and not set(radio.heard) - {uvk5.HELLO, uvk5.READ}   # read-only


def test_a_backup_whose_two_reads_disagree_saves_nothing(tmp_path):
    with FakeRadio(flip_on_pass=2) as radio:
        port = uvk5.Port(radio.path)
        try:
            with pytest.raises(uvk5.RadioError, match="disagree from 0x0403"):
                uvk5.backup(port, tmp_path)
        finally:
            port.close()
    assert list(tmp_path.iterdir()) == []


def test_bootloader_version_is_heard_without_sending_anything():
    with FakeRadio(mode="bootloader") as radio:
        port = uvk5.Port(radio.path)
        try:
            assert uvk5.bootloader_version(port, timeout=3) == "2.00.06"
        finally:
            port.close()
        assert radio.heard == []
    assert "classic" in uvk5.bootloader_verdict("2.00.06")
    assert "Do NOT flash" in uvk5.bootloader_verdict("5.00.01")


def test_a_silent_radio_times_out_with_a_reason():
    with FakeRadio(mode="silent") as radio:
        port = uvk5.Port(radio.path)
        try:
            with pytest.raises(uvk5.RadioError, match="radio on"):
                uvk5.hello(port, tries=1)
        finally:
            port.close()
