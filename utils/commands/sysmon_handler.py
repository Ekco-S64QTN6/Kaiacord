"""
!sysmon Command Handler
=======================

Owner-only. Displays live system metrics, UFW status, open ports,
and recent SSH activity in a premium Discord Embed card. Also writes
a snapshot to the knowledge base so Kaia can recall historical anomalies via RAG.
"""

import os
import time
import asyncio
from datetime import datetime
from pathlib import Path

import discord
import psutil

from utils.infrastructure.logging.kaia_logger import log_action, log_error
from utils.infrastructure.system.kaia_sysmon import (
    build_sysmon_report_async,
    collect_system_state_async,
    _parse_ports,
    _run_cmd_async,
)
from utils.infrastructure.monitoring.stats_poller import stats_poller
from utils.infrastructure.monitoring.stats_tracker import stats_tracker

# Where snapshots go for RAG indexing
_SYSMON_LOG_DIR = Path("knowledge_base/system_logs")


def _count_recent_hallucinations(log_path: str = "memory/hallucination_log.jsonl", seconds: int = 86400) -> int:
    """Count entries in hallucination_log.jsonl from the last N seconds."""
    count = 0
    now = time.time()
    if not os.path.exists(log_path):
        return 0
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    import json
                    data = json.loads(line)
                    ts = data.get('timestamp')
                    if ts and (now - ts) < seconds:
                        count += 1
                except Exception:
                    continue
    except Exception:
        pass
    return count


def _make_ansi_bar(pct: float, width: int = 15) -> str:
    """Generate a premium ANSI-colored progress bar using ▰ and ▱."""
    filled = max(0, min(width, int((pct / 100) * width)))
    bar_str = ""
    for i in range(width):
        if i < filled:
            pos_pct = (i / width) * 100
            if pos_pct < 50:
                color = "32" # Green
            elif pos_pct < 80:
                color = "33" # Yellow
            else:
                color = "31" # Red
            bar_str += f"\u001b[{color}m▰\u001b[0m"
        else:
            bar_str += "\u001b[30m▱\u001b[0m"
    return bar_str


def _color_value(val_str: str, pct: float) -> str:
    """Color a value string based on percentage."""
    if pct < 50:
        color = "32" # Green
    elif pct < 80:
        color = "33" # Yellow
    else:
        color = "31" # Red
    return f"\u001b[1;{color}m{val_str}\u001b[0m"


def _make_text_bar(pct: float, width: int = 10) -> str:
    """Generate a clean progress bar using ▰ and ▱."""
    filled = max(0, min(width, int((pct / 100) * width)))
    return "▰" * filled + "▱" * (width - filled)


def _get_status_emoji(pct: float) -> str:
    """Get emoji based on percentage."""
    if pct < 50:
        return "🟢"
    elif pct < 80:
        return "🟡"
    else:
        return "🔴"



async def handle_sysmon_command(ctx, msg, send_kaia_response):
    """Handle the !sysmon command (owner only)."""
    is_owner = ctx.config.is_owner(
        msg.author.name, msg.author.display_name, str(msg.author.id)
    )
    if not is_owner:
        await msg.channel.send("```\nrestricted. admins only.\n```")
        return

    log_action(f"!sysmon requested by {msg.author.display_name}")

    # Send a quick typing indicator or message since we sample network over 0.5s
    async with msg.channel.typing():
        try:
            # 1. Fetch system state concurrently with background commands
            sys_state_task = asyncio.create_task(collect_system_state_async())
            
            # Measure network delta over 0.5s
            t0 = time.time()
            net0 = psutil.net_io_counters()
            await asyncio.sleep(0.5)
            t1 = time.time()
            net1 = psutil.net_io_counters()
            
            sys_state = await sys_state_task
            
            # Compute dynamic throughput
            elapsed = t1 - t0
            net_recv_kbs = 0.0
            net_sent_kbs = 0.0
            if elapsed > 0.1:
                net_recv_kbs = max(0.0, (net1.bytes_recv - net0.bytes_recv) / 1024.0 / elapsed)
                net_sent_kbs = max(0.0, (net1.bytes_sent - net0.bytes_sent) / 1024.0 / elapsed)
                
            net_total_recv_gb = net1.bytes_recv / (1024 ** 3)
            net_total_sent_gb = net1.bytes_sent / (1024 ** 3)
            
            # Fetch UFW rules and SSH activity in background
            ufw_detail, auth_log = await asyncio.gather(
                _run_cmd_async(["sudo", "ufw", "status", "verbose"]),
                _run_cmd_async(["sudo", "journalctl", "-u", "sshd", "-n", "6", "--no-pager", "-q"]),
            )
            if not auth_log:
                auth_log = await _run_cmd_async(["sudo", "tail", "-n", "6", "/var/log/auth.log"])

            # 2. Query stats poller & tracker
            p_stats = stats_poller.get_stats()
            t_stats = stats_tracker.get_stats()

            # 3. Pull dynamic RAG health
            rag = getattr(ctx, 'rag', None)
            bot_state = getattr(ctx, 'bot_state', None)
            
            rag_confidence = 0.0
            rag_nodes = 0
            coherence_ema = 0.85
            rag_stale = True
            
            if rag:
                rag_confidence = getattr(rag, '_last_retrieval_confidence', 0.0)
                rag_nodes = getattr(rag, '_last_retrieval_node_count', 0)
                last_query_time = getattr(rag, '_last_retrieval_time', 0.0)
                if last_query_time and (time.time() - last_query_time) < 900:
                    rag_stale = False
                    
            if bot_state:
                coherence_ema = getattr(bot_state, 'kaia_coherence', 0.85)

            h_count = _count_recent_hallucinations()

            # 4. Generate traditional markdown report to write to RAG system logs
            traditional_report = await build_sysmon_report_async()
            _write_sysmon_snapshot(traditional_report)

        except Exception as e:
            log_error(f"!sysmon diagnostics failed: {e}")
            await send_kaia_response(msg.channel, "system monitor diagnostics failed.")
            return

    # Build the Embed layout
    cpu_pct = sys_state.get('cpu_pct', 0.0)
    ram_pct = sys_state.get('ram_pct', 0.0)
    ram_used = sys_state.get('ram_used_gb', 0.0)
    ram_total = sys_state.get('ram_total_gb', 0.0)
    
    vram_used = sys_state.get('vram_used_gb', 0.0)
    vram_total = sys_state.get('vram_total_gb', 0.0)
    vram_pct = (vram_used / vram_total * 100) if vram_total > 0 else 0.0
    
    disk_pct = sys_state.get('disk_pct', 0.0)
    disk_used = sys_state.get('disk_used_gb', 0.0)
    disk_total = sys_state.get('disk_total_gb', 0.0)
    gpu_name = sys_state.get('gpu_name', 'NVIDIA GPU')

    embed = discord.Embed(
        title="🖥️ Kaia System Dashboard",
        description=(
            f"**Host**: `ekco@kaia` | **Status**: `ONLINE`\n"
            f"**Uptime**: `{sys_state.get('uptime', 'unknown')}` | **Active Model**: `{p_stats.get('active_model', 'None')}`"
        ),
        color=0x00d2ff,
        timestamp=datetime.now()
    )

    # 1. Hardware utilization
    sys_lines = [
        f"**CPU:** `[{_make_text_bar(cpu_pct)}]` **{cpu_pct:.1f}%**",
        f"**RAM:** `[{_make_text_bar(ram_pct)}]` **{ram_pct:.1f}%** *({ram_used:.1f}/{ram_total:.1f} GB)*",
        f"**GPU:** `[{_make_text_bar(vram_pct)}]` **{vram_pct:.1f}%** *({vram_used:.1f}/{vram_total:.1f} GB)*",
        f"**Disk:** `[{_make_text_bar(disk_pct)}]` **{disk_pct:.1f}%** *({disk_used:.1f}/{disk_total:.1f} GB)*",
    ]

    # 2. LLM Inference Models
    models_list = p_stats.get('ollama_models', [])
    if models_list:
        model_bullets = []
        for m in models_list:
            model_bullets.append(f"`{m}`")
        models_str = ", ".join(model_bullets)
    else:
        models_str = "*None loaded*"

    # 3. Network Activity
    core_sys_value = (
        "\n".join(sys_lines) + "\n\n"
        f"**Loaded Models:** {models_str}\n"
        f"**Network Rate:** ▼ `{net_recv_kbs:.1f} KB/s`  |  ▲ `{net_sent_kbs:.1f} KB/s`\n"
        f"**Network Total:** ⬇ `{net_total_recv_gb:.2f} GB`  |  ⬆ `{net_total_sent_gb:.2f} GB`"
    )

    embed.add_field(
        name="📊 Core System Status",
        value=core_sys_value,
        inline=False
    )

    # 4. Bot Metrics
    msgs = t_stats.get('messages', 0)
    active_users = t_stats.get('active_users_display', '0 (idle)')
    avg_resp = t_stats.get('avg_response_time', 0.0)
    q_size = t_stats.get('queue_size', 0)

    bot_perf_str = (
        f"• **Messages:** `{msgs:,}`\n"
        f"• **Active Users:** `{active_users}`\n"
        f"• **Avg Response:** `{avg_resp:.2f}s`\n"
        f"• **Queue Size:** `{q_size}`"
    )

    # 5. Cognitive Pipeline
    beliefs_cnt = p_stats.get('beliefs_count', 0)
    anchors_cnt = p_stats.get('anchors_count', 0)
    rel_cnt = p_stats.get('relationship_count', 0)
    dreams_cnt = p_stats.get('dreams_count', 0)

    cog_str = (
        f"• **Beliefs:** `{beliefs_cnt}/50`\n"
        f"• **Memory Anchors:** `{anchors_cnt}/50`\n"
        f"• **Relationships:** `{rel_cnt} users`\n"
        f"• **Dreams Count:** `{dreams_cnt} mems`"
    )

    # 6. RAG Health
    conf_pct = rag_confidence * 100
    rag_stale_text = "*(stale)*" if rag_stale else ""
    rag_conf_bar = _make_text_bar(conf_pct, 10)

    rag_str = (
        f"• **Confidence:** `[{rag_conf_bar}]` **{rag_confidence:.2f}** {rag_stale_text}\n"
        f"• **Coherence:** **{coherence_ema:.3f}**\n"
        f"• **Hallucinations (24h):** **{h_count}**\n"
        f"• **Knowledge Base:** `{p_stats.get('indexed_files', 0)} files` *({p_stats.get('rag_size', '0 MB')})*"
    )

    # 7. Forum Operations
    drafts = t_stats.get('forum_drafts', 0)
    approved = t_stats.get('forum_approved', 0)
    rejected = t_stats.get('forum_rejected', 0)

    forum_str = (
        f"• **Drafts:** `{drafts}`\n"
        f"• **Approved:** `{approved}`\n"
        f"• **Rejected:** `{rejected}`"
    )

    bot_cog_value = (
        f"**Performance:**\n{bot_perf_str}\n\n"
        f"**Cognitive Pipeline:**\n{cog_str}\n\n"
        f"**RAG & Continuity:**\n{rag_str}\n\n"
        f"**Forum Operations:**\n{forum_str}"
    )

    embed.add_field(
        name="🧠 Bot & Cognitive Metrics",
        value=bot_cog_value,
        inline=False
    )

    # 8. Security & Ports
    ufw_status_str = "ACTIVE" if sys_state.get('ufw_status') == "active" else "INACTIVE"
    ports_total = sys_state.get('open_port_count', 0)
    security_title = f"🛡️ Security & Ports  |  Firewall: {ufw_status_str}  |  {ports_total} ports"

    port_bullets = []
    ss_raw = sys_state.get("_ss_raw", "")
    if ss_raw:
        parsed_ports = _parse_ports(ss_raw)
        for p in parsed_ports[:6]:
            addr_pretty = "localhost" if p['addr'] in ("127.0.0.1", "::1") else ("*" if p['addr'] in ("0.0.0.0", "*", "::") else p['addr'])
            port_bullets.append(f"• `:{p['port']:<5}` ➜ **{p['proc']}** *({addr_pretty})*")
        if len(parsed_ports) > 6:
            port_bullets.append(f"• *... and {len(parsed_ports) - 6} more listening ports*")
    else:
        port_bullets.append("• *No listening ports detected*")
    ports_str = "\n".join(port_bullets)

    ssh_bullets = []
    if auth_log:
        for line in auth_log.splitlines()[:5]:
            if not line.strip():
                continue
            ssh_bullets.append(f"• `{line.strip()}`")
    else:
        ssh_bullets.append("• *No recent SSH log activity*")
    ssh_str = "\n".join(ssh_bullets)

    security_value = (
        "**Active Listeners:**\n"
        + ports_str + "\n\n"
        "**Recent Activity:**\n"
        + ssh_str
    )

    embed.add_field(
        name=security_title,
        value=security_value,
        inline=False
    )
    
    embed.set_footer(text=f"ekco@kaia | GPU: {gpu_name}")

    await msg.channel.send(embed=embed)


def _write_sysmon_snapshot(report: str):
    """
    Write a timestamped snapshot to knowledge_base/system_logs/
    so Kaia can recall system history through RAG.
    """
    try:
        _SYSMON_LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        snapshot_path = _SYSMON_LOG_DIR / f"sysmon_{today}.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n## Snapshot: {timestamp}\n```\n{report}\n```\n"

        with open(snapshot_path, "a", encoding="utf-8") as f:
            if snapshot_path.stat().st_size == 0 if snapshot_path.exists() else False:
                f.write(f"# System Monitor Log — {today}\n")
            f.write(entry)
    except Exception as e:
        log_error(f"Failed to write sysmon snapshot: {e}")

