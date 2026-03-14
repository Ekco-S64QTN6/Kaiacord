"""
Kaia System Monitor
===================

Collects real hardware/OS state for prompt injection and !sysmon command.
All operations are read-only. No system writes occur here.

Machine: ekco@kaia (RTX 3060, local Ollama inference)
Firewall: UFW
"""

import asyncio
import os
import socket
import subprocess
import time
import re
from functools import lru_cache
from typing import Optional

import psutil

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_cmd(cmd: list[str], timeout: int = 5) -> str:
    """Run a shell command, return stdout string or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


async def _run_cmd_async(cmd: list[str], timeout: int = 5) -> str:
    """Run a shell command async — never blocks the event loop."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode("utf-8", errors="replace").strip()
        except asyncio.TimeoutError:
            proc.kill()
            return ""
    except Exception:
        return ""


def _uptime_str() -> str:
    """Return human-readable uptime string."""
    try:
        seconds = time.time() - psutil.boot_time()
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        if h >= 24:
            return f"{h // 24}d {h % 24}h"
        return f"{h}h {m}m"
    except Exception:
        return "unknown"


def _vram_info() -> tuple[float, float]:
    """Return (used_gb, total_gb) from nvidia-smi, or (0, 0) on failure."""
    raw = _run_cmd(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total",
         "--format=csv,noheader,nounits"]
    )
    if not raw:
        return 0.0, 0.0
    try:
        used_mb, total_mb = (float(x.strip()) for x in raw.split(","))
        return round(used_mb / 1024, 1), round(total_mb / 1024, 1)
    except Exception:
        return 0.0, 0.0


def _gpu_name() -> str:
    """Return GPU name string."""
    return _run_cmd(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
    ) or "unknown GPU"


def _open_port_count() -> int:
    """Return count of listening TCP ports."""
    raw = _run_cmd(["sudo", "ss", "-tlnp"])
    if not raw:
        return -1
    # Count lines that start with LISTEN
    return sum(1 for line in raw.splitlines() if line.startswith("LISTEN"))


def _parse_ports(ss_output: str) -> list[dict]:
    """Parse ss -tlnp output into clean port/process dicts."""
    results = []
    for line in ss_output.splitlines():
        if not line.startswith("LISTEN"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[3]
        # Extract port from addr:port
        port_match = re.search(r':(\d+)$', local_addr)
        if not port_match:
            continue
        port = port_match.group(1)
        # Extract address (127.0.0.1, 0.0.0.0, ::1, etc)
        addr = local_addr.rsplit(":", 1)[0].strip("[]") or "*"
        # Extract process name from users:(("name",pid=...))
        proc = "system"
        users_match = re.search(r'users:\(\("([^"]+)"', line)
        if users_match:
            proc = users_match.group(1)
            # Clean up binary names
            proc = proc.replace(".bin", "").replace("_server", "")
        results.append({"port": int(port), "addr": addr, "proc": proc})
    # Sort by port number
    results.sort(key=lambda x: x["port"])
    return results


def _bar(pct: float, width: int = 10) -> str:
    """Simple ASCII progress bar."""
    filled = int((pct / 100) * width)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def _ufw_status_full() -> tuple[str, str]:
    """
    Returns (summary, detail) both from the same sudo call.
    Avoids the inconsistency of calling ufw twice.
    """
    raw = _run_cmd(["sudo", "ufw", "status", "verbose"])
    if not raw:
        return "unknown", "unavailable"
    first_line = raw.splitlines()[0].lower()
    summary = "active" if "active" in first_line else "inactive"
    # Trim to relevant rules only (skip preamble after line 3)
    lines = [l for l in raw.splitlines() if l.strip()]
    detail = "\n".join(lines[:30])
    return summary, detail


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_system_state() -> dict:
    """
    Collect current system state. Cheap enough to call per-message.
    Returns a dict with all relevant metrics.
    """
    hostname = socket.gethostname()  # "kaia"
    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    ram_used_gb = round(mem.used / (1024 ** 3), 1)
    ram_total_gb = round(mem.total / (1024 ** 3), 1)
    ram_pct = mem.percent
    disk = psutil.disk_usage("/")
    disk_used_gb = round(disk.used / (1024 ** 3), 1)
    disk_total_gb = round(disk.total / (1024 ** 3), 1)
    disk_pct = disk.percent
    vram_used, vram_total = _vram_info()
    uptime = _uptime_str()
    open_ports = _open_port_count()
    ufw_summary, _ = _ufw_status_full()
    gpu_name = _gpu_name()

    return {
        "hostname": hostname,
        "uptime": uptime,
        "cpu_pct": cpu_pct,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "ram_pct": ram_pct,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_pct": disk_pct,
        "vram_used_gb": vram_used,
        "vram_total_gb": vram_total,
        "gpu_name": gpu_name,
        "open_port_count": open_ports,
        "ufw_status": ufw_summary,
    }


def build_system_prompt_block(state: Optional[dict] = None) -> str:
    """
    Build the [SYSTEM STATE] block injected into Kaia's system prompt.
    Kept intentionally compact — one paragraph of facts, no fluff.
    """
    if state is None:
        state = collect_system_state()

    hostname = state.get("hostname", "kaia")
    uptime = state.get("uptime", "unknown")
    cpu = state.get("cpu_pct", 0.0)
    ram_used = state.get("ram_used_gb", 0.0)
    ram_total = state.get("ram_total_gb", 0.0)
    vram_used = state.get("vram_used_gb", 0.0)
    vram_total = state.get("vram_total_gb", 0.0)
    disk_used = state.get("disk_used_gb", 0.0)
    disk_total = state.get("disk_total_gb", 0.0)
    ports = state.get("open_port_count", -1)
    ufw = state.get("ufw_status", "unknown")
    gpu = state.get("gpu_name", "GPU")

    ports_str = f"{ports} listening ports" if ports >= 0 else "port count unavailable"

    return (
        f"[HOST STATE — {hostname}]\n"
        f"uptime: {uptime} | cpu: {cpu:.0f}% | "
        f"ram: {ram_used}/{ram_total}GB | "
        f"vram: {vram_used}/{vram_total}GB ({gpu}) | "
        f"disk: {disk_used}/{disk_total}GB | "
        f"network: {ports_str} | firewall: {ufw}"
    )


async def collect_system_state_async() -> dict:
    """Async version — safe to call from the event loop."""
    hostname = socket.gethostname()
    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    ram_used_gb = round(mem.used / (1024 ** 3), 1)
    ram_total_gb = round(mem.total / (1024 ** 3), 1)
    ram_pct = mem.percent
    disk = psutil.disk_usage("/")
    disk_used_gb = round(disk.used / (1024 ** 3), 1)
    disk_total_gb = round(disk.total / (1024 ** 3), 1)
    disk_pct = disk.percent

    # Run all subprocess calls concurrently
    vram_raw, gpu_raw, ss_raw, ufw_raw = await asyncio.gather(
        _run_cmd_async(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                        "--format=csv,noheader,nounits"]),
        _run_cmd_async(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]),
        _run_cmd_async(["sudo", "ss", "-tlnp"]),
        _run_cmd_async(["sudo", "ufw", "status"]),
    )

    # Parse VRAM
    vram_used, vram_total = 0.0, 0.0
    if vram_raw:
        try:
            used_mb, total_mb = (float(x.strip()) for x in vram_raw.split(","))
            vram_used, vram_total = round(used_mb / 1024, 1), round(total_mb / 1024, 1)
        except Exception:
            pass

    # Parse UFW summary
    ufw_status = "unknown"
    if ufw_raw:
        first = ufw_raw.splitlines()[0].lower()
        ufw_status = "active" if "active" in first else "inactive"

    # Parse port count
    open_ports = sum(1 for l in ss_raw.splitlines() if l.startswith("LISTEN")) if ss_raw else -1

    return {
        "hostname": hostname,
        "uptime": _uptime_str(),
        "cpu_pct": cpu_pct,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "ram_pct": ram_pct,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_pct": disk_pct,
        "vram_used_gb": vram_used,
        "vram_total_gb": vram_total,
        "gpu_name": gpu_raw or "unknown GPU",
        "open_port_count": open_ports,
        "ufw_status": ufw_status,
        "_ss_raw": ss_raw,  # pass through so build_sysmon_report doesn't call ss twice
    }


def _format_sysmon_report(state: dict, ss_raw: str, ufw_detail: str, auth_log: str) -> str:
    """Pure formatting logic separated out for use by async and sync variants."""
    hostname  = state["hostname"]
    uptime    = state["uptime"]
    cpu       = state["cpu_pct"]
    ram_used  = state["ram_used_gb"]
    ram_total = state["ram_total_gb"]
    ram_pct   = state["ram_pct"]
    vram_used = state["vram_used_gb"]
    vram_total= state["vram_total_gb"]
    vram_pct  = (vram_used / vram_total * 100) if vram_total > 0 else 0
    disk_used = state["disk_used_gb"]
    disk_total= state["disk_total_gb"]
    disk_pct  = state["disk_pct"]
    gpu       = state["gpu_name"]
    ports     = state["open_port_count"]
    ufw_summary = state["ufw_status"]

    ports_detail = "unavailable"
    if ss_raw:
        parsed = _parse_ports(ss_raw)
        if parsed:
            def _pretty_addr(a):
                if a in ("127.0.0.1", "::1"): return "localhost"
                if a in ("0.0.0.0", "*", "::"): return "*"
                return a
            
            plines = [f"  :{p['port']:<6} {_pretty_addr(p['addr']):<13} {p['proc']}" for p in parsed]
            ports_detail = "\n".join(plines)
        else:
            ports_detail = "  (no ports listening)"

    if not auth_log:
        auth_log_fmt = "  unavailable"
    else:
        auth_log_fmt = "\n".join(f"  {line}" for line in auth_log.splitlines())

    sep = "────────────────────────────────────────────────────"
    
    lines = [
        f"  SYSTEM MONITOR  {hostname}  uptime: {uptime}",
        sep,
        f"  CPU   {_bar(cpu)} {cpu:.0f}%",
        f"  RAM   {_bar(ram_pct)} {ram_pct:.0f}%  {ram_used}/{ram_total} GB",
        f"  VRAM  {_bar(vram_pct)} {vram_pct:.0f}%  {vram_used}/{vram_total} GB  ({gpu})",
        f"  DISK  {_bar(disk_pct)} {disk_pct:.0f}%  {disk_used}/{disk_total} GB",
        sep,
        f"  FIREWALL  UFW {ufw_summary.upper()}",
        sep,
        "\n".join(f"  {row}" for row in ufw_detail.splitlines()) if ufw_detail.strip() and ufw_detail != "unavailable" else "  (no rules defined)",
        sep,
        f"  LISTENING PORTS  ({ports if ports >= 0 else 'unknown'} total)",
        sep,
        ports_detail,
        sep,
        "  RECENT SSH ACTIVITY",
        sep,
        auth_log_fmt,
    ]
    return "\n".join(lines)


def build_sysmon_report() -> str:
    """
    Build the full !sysmon Discord report.
    """
    state = collect_system_state()
    
    # Retrieve unified UFW status
    ufw_summary, ufw_detail = _ufw_status_full()
    state["ufw_status"] = ufw_summary # ensure consistency
    
    # Parse ports into a readable table
    raw_ports = _run_cmd(["sudo", "ss", "-tlnp"])

    # Journalctl for SSHD (handling auth failures)
    auth_log = _run_cmd(
        ["sudo", "journalctl", "-u", "sshd", "-n", "20", "--no-pager", "-q"]
    )
    if not auth_log:
        auth_log = _run_cmd(["sudo", "tail", "-n", "20", "/var/log/auth.log"])

    return _format_sysmon_report(state, raw_ports, ufw_detail, auth_log)


async def build_sysmon_report_async() -> str:
    """Async version of build_sysmon_report."""
    state = await collect_system_state_async()
    ss_raw = state.pop("_ss_raw", "")

    # Remaining subprocess calls — run concurrently
    ufw_detail, auth_log = await asyncio.gather(
        _run_cmd_async(["sudo", "ufw", "status", "verbose"]),
        _run_cmd_async(["sudo", "journalctl", "-u", "sshd", "-n", "15",
                        "--no-pager", "-q"]),
    )
    if not auth_log:
        auth_log = await _run_cmd_async(["sudo", "tail", "-n", "15", "/var/log/auth.log"])

    return _format_sysmon_report(state, ss_raw, ufw_detail, auth_log)


async def build_system_prompt_block_async() -> str:
    """Async version for message_processor injection."""
    state = await collect_system_state_async()
    state.pop("_ss_raw", None)
    return build_system_prompt_block(state)  # formatting is pure, reuse sync version
