#!/usr/bin/env python3
"""Quansheng UV-K5 over its K-plug programming cable — read-only.

    uvk5.py ports               find the cable, and say why it can't be used if it can't
    uvk5.py info                firmware version (radio on, normal mode)
    uvk5.py backup [--out DIR]  the whole 8 KB EEPROM, calibration included, read twice and compared
    uvk5.py bootloader          bootloader version (radio started holding PTT) — which hardware it is

Nothing here writes to the radio. The backup is the step before any flash:
the calibration at 0x1E00–0x1FFF is set per radio at the factory, and a
firmware or channel tool that overwrites it leaves a radio that is off
frequency and off power with nothing to restore it from.

Protocol (as CHIRP's uvk5 driver speaks it): 38400 8N1; a frame is AB CD,
a 16-bit little-endian payload length, the payload and its CRC-16/XMODEM
XOR'd with a 16-byte key, then DC BA. Hello is 0x0514 (reply 0x0515 carries
the firmware version), EEPROM read is 0x051B (reply 0x051C), and a radio in
bootloader mode announces itself unasked with 0x0518 frames carrying the
bootloader version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import select
import struct
import sys
import termios
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "memory" / "radio" / "uvk5"

KEY = bytes([0x16, 0x6C, 0x14, 0xE6, 0x2E, 0x91, 0x0D, 0x40,
             0x21, 0x35, 0xD5, 0x40, 0x13, 0x03, 0xE9, 0x80])
SESSION = b"\x6a\x39\x57\x64"
EEPROM_SIZE = 0x2000
CAL_START = 0x1E00
BLOCK = 0x80

HELLO, HELLO_REPLY = 0x0514, 0x0515
READ, READ_REPLY = 0x051B, 0x051C
BOOT_BEACON = 0x0518

#: USB serial chips K-plug cables are built on (and the AIOC, which is a
#: sound card, serial port and PTT in one).
CHIPS = {
    ("0403", "6001"): "FTDI FT232R", ("0403", "6015"): "FTDI FT230X",
    ("1a86", "7523"): "CH340", ("1a86", "55d3"): "CH343",
    ("067b", "2303"): "Prolific PL2303", ("10c4", "ea60"): "Silicon Labs CP210x",
    ("1209", "7388"): "AIOC (audio + serial + PTT)",
}


class RadioError(Exception):
    pass


# ── framing ──────────────────────────────────────────────────────────────

def xor(data: bytes) -> bytes:
    return bytes(b ^ KEY[i % 16] for i, b in enumerate(data))


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def frame(payload: bytes) -> bytes:
    body = payload + struct.pack("<H", crc16_xmodem(payload))
    return b"\xab\xcd" + struct.pack("<H", len(payload)) + xor(body) + b"\xdc\xba"


def message(cmd: int, body: bytes) -> bytes:
    return struct.pack("<HH", cmd, len(body)) + body


class Port:
    """A raw tty at 38400 8N1, with timeouts. termios rather than pyserial:
    the venv has no pyserial, and this is all it needs."""

    def __init__(self, path: str, baud: int = 38400):
        self.path = path
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except PermissionError:
            raise RadioError(f"{path}: permission denied — {_permission_hint()}")
        tty.setraw(self.fd)
        attrs = termios.tcgetattr(self.fd)
        speed = getattr(termios, f"B{baud}")
        attrs[4] = attrs[5] = speed
        attrs[2] &= ~(termios.CSTOPB | termios.PARENB | getattr(termios, "CRTSCTS", 0))
        attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.buf = b""

    def close(self):
        os.close(self.fd)

    def write(self, data: bytes):
        os.write(self.fd, data)

    def read_frame(self, timeout: float = 1.0) -> bytes:
        """The next frame's payload, de-obfuscated, without its CRC."""
        end = time.monotonic() + timeout
        while True:
            start = self.buf.find(b"\xab\xcd")
            if start >= 0 and len(self.buf) >= start + 4:
                n = struct.unpack("<H", self.buf[start + 2:start + 4])[0]
                total = 4 + n + 4
                if len(self.buf) >= start + total:
                    raw = self.buf[start:start + total]
                    self.buf = self.buf[start + total:]
                    if raw[-2:] != b"\xdc\xba":
                        continue                                  # misaligned: look for the next header
                    return xor(raw[4:4 + n])
            left = end - time.monotonic()
            if left <= 0:
                raise RadioError("no answer from the radio (timeout)")
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    self.buf += os.read(self.fd, 4096)
                except BlockingIOError:
                    pass
            if len(self.buf) > 65536:
                self.buf = self.buf[-4096:]

    def ask(self, cmd: int, body: bytes, want: int, timeout: float = 1.0) -> bytes:
        self.write(frame(message(cmd, body)))
        end = time.monotonic() + timeout
        while True:
            reply = self.read_frame(max(0.05, end - time.monotonic()))
            if len(reply) >= 4 and struct.unpack("<H", reply[:2])[0] == want:
                return reply


# ── what the radio says ──────────────────────────────────────────────────

def hello(port: Port, tries: int = 5) -> str:
    last = None
    for _ in range(tries):
        try:
            reply = port.ask(HELLO, SESSION, HELLO_REPLY)
            return reply[4:20].split(b"\x00")[0].decode("ascii", "replace").strip()
        except RadioError as e:
            last = e
    raise RadioError(f"{last} — is the radio on (not in bootloader mode) and the plug pressed fully home?")


def read_eeprom(port: Port, start: int = 0, size: int = EEPROM_SIZE) -> bytes:
    out = bytearray()
    for off in range(start, start + size, BLOCK):
        n = min(BLOCK, start + size - off)
        reply = port.ask(READ, struct.pack("<HBB", off, n, 0) + SESSION, READ_REPLY)
        got_off, got_n = struct.unpack("<HB", reply[4:7])
        data = reply[8:8 + got_n]
        if got_off != off or len(data) != n:
            raise RadioError(f"asked for {n} bytes at 0x{off:04X}, got {len(data)} at 0x{got_off:04X}")
        out += data
    return bytes(out)


VERSION = re.compile(rb"\d{1,2}\.\d{2}\.\d{2}")


def bootloader_version(port: Port, timeout: float = 6.0) -> str:
    """Listen (send nothing) for the beacon a radio in bootloader mode repeats."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            payload = port.read_frame(max(0.05, end - time.monotonic()))
        except RadioError:
            break
        if len(payload) >= 4 and struct.unpack("<H", payload[:2])[0] == BOOT_BEACON:
            m = VERSION.search(payload)
            return m.group(0).decode() if m else "unknown (beacon seen, no version in it)"
    raise RadioError("no bootloader beacon — power the radio on while holding PTT (the flashlight LED lights)")


def bootloader_verdict(version: str) -> str:
    if version.startswith("2."):
        return ("classic UV-K5 (DP32G030 MCU): the standard F4HWN / egzumer builds are for this radio")
    return ("not the classic 2.x bootloader — likely a newer UV-K5 hardware revision. Do NOT flash a "
            "standard build: find the firmware release that names this bootloader version first")


# ── the cable ────────────────────────────────────────────────────────────

def _usb_ids(tty_name: str):
    d = Path(f"/sys/class/tty/{tty_name}/device").resolve()
    for p in [d, *d.parents]:
        if (p / "idVendor").exists():
            return ((p / "idVendor").read_text().strip(), (p / "idProduct").read_text().strip())
    return None


def _permission_hint() -> str:
    import grp
    try:
        members = grp.getgrnam("uucp").gr_mem
    except KeyError:
        return "check the device's group with ls -l"
    user = os.environ.get("USER", "")
    if user in members:
        return "you are in uucp but this session isn't — log out and back in"
    return f"run: sudo usermod -aG uucp {user or '$USER'}, then log out and back in"


def kernel_problem() -> str:
    release = os.uname().release
    if not Path(f"/lib/modules/{release}").exists():
        return (f"the running kernel ({release}) has no modules on disk — an upgrade replaced them, so no "
                "USB-serial driver can load. Reboot before plugging the cable in.")
    return ""


def find_ports() -> list:
    found = []
    for tty_dir in sorted(Path("/sys/class/tty").glob("tty*")):
        if not (tty_dir.name.startswith("ttyUSB") or tty_dir.name.startswith("ttyACM")):
            continue
        ids = _usb_ids(tty_dir.name)
        dev = f"/dev/{tty_dir.name}"
        found.append({"port": dev, "ids": ":".join(ids) if ids else "?",
                      "chip": CHIPS.get(ids, "unknown USB serial") if ids else "?",
                      "access": os.access(dev, os.R_OK | os.W_OK)})
    return found


def pick_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    ports = [p for p in find_ports() if p["chip"] != "?"]
    if not ports:
        raise RadioError(kernel_problem() or "no USB serial cable found — is it plugged in?")
    if len(ports) > 1:
        raise RadioError("more than one serial cable: pass --port " + " | ".join(p["port"] for p in ports))
    return ports[0]["port"]


# ── backup ───────────────────────────────────────────────────────────────

def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def backup(port: Port, out_dir: Path) -> Path:
    firmware = hello(port)
    first = read_eeprom(port)
    second = read_eeprom(port)
    if first != second:
        diff = next(i for i in range(len(first)) if first[i] != second[i])
        raise RadioError(f"two reads disagree from 0x{diff:04X} — the plug may be loose; nothing was saved")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", firmware) or "unknown"
    path = out_dir / f"{stamp}_{name}_eeprom.bin"
    if path.exists():
        raise RadioError(f"{path} already exists")
    _write_bytes_atomic(path, first)
    _write_bytes_atomic(path.with_suffix(".json"), json.dumps({
        "firmware": firmware, "read_at": stamp, "bytes": len(first),
        "sha256": hashlib.sha256(first).hexdigest(),
        "calibration": {"range": f"0x{CAL_START:04X}-0x{EEPROM_SIZE - 1:04X}",
                        "sha256": hashlib.sha256(first[CAL_START:]).hexdigest(),
                        "blank": first[CAL_START:] in (b"\xff" * (EEPROM_SIZE - CAL_START),
                                                       b"\x00" * (EEPROM_SIZE - CAL_START))},
    }, indent=2).encode())
    return path


# ── CLI ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["ports", "info", "backup", "bootloader"])
    ap.add_argument("--port", help="serial device (default: the one cable plugged in)")
    ap.add_argument("--out", type=Path, default=BACKUP_DIR, help=f"backup folder (default {BACKUP_DIR})")
    args = ap.parse_args(argv)

    if args.command == "ports":
        problem = kernel_problem()
        if problem:
            print("!!", problem)
        ports = find_ports()
        if not ports:
            print("no USB serial ports" + ("" if problem else " — plug the cable in"))
            return 1
        for p in ports:
            ok = "ok" if p["access"] else "NO ACCESS — " + _permission_hint()
            print(f"{p['port']}  {p['ids']}  {p['chip']}  {ok}")
        return 0 if all(p["access"] for p in ports) else 1

    try:
        port = Port(pick_port(args.port))
        try:
            if args.command == "info":
                print(f"firmware: {hello(port)}")
            elif args.command == "bootloader":
                v = bootloader_version(port)
                print(f"bootloader: {v}\n{bootloader_verdict(v)}")
            else:
                path = backup(port, args.out)
                meta = json.loads(path.with_suffix(".json").read_text())
                print(f"saved {meta['bytes']} bytes to {path}\nfirmware {meta['firmware']}, "
                      f"sha256 {meta['sha256'][:16]}…, calibration sha256 {meta['calibration']['sha256'][:16]}…")
                if meta["calibration"]["blank"]:
                    print("!! the calibration region is blank — do not flash until that is understood")
                    return 2
        finally:
            port.close()
    except RadioError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
