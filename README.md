<div align="center">

# Kaiacord

**A self-hosted Discord bot with a persistent inner life, running on one consumer GPU.**

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.7.1-5865F2.svg?style=flat-square&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Ollama](https://img.shields.io/badge/Inference-Ollama-black.svg?style=flat-square)](https://ollama.com)
[![Model](https://img.shields.io/badge/Model-gemma3%3A12b-4285F4.svg?style=flat-square)](https://ollama.com/library/gemma3)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

[Features](#features) · [Quick start](#quick-start) · [Documentation](#documentation) · [Roadmap](docs/ROADMAP.md)

</div>

---

Kaia is a Discord bot built to feel less like a chatbot and more like someone who lives in the
server. She remembers. Her mood carries from one conversation to the next, she knows each person
differently, she forms opinions and sometimes changes them, and every night she turns the day's
conversations into long-term memory.

Everything that thinks runs on your own hardware: one 12 GB GPU serves the language model and
embeddings run on the CPU. No hosted model, no per-token bill.

| | |
|:--|:--|
| **Continuity** | Mood, relationships, beliefs and episodic memories persist to disk and survive restarts. |
| **Grounded answers** | Hybrid BM25 and vector retrieval over a curated Markdown knowledge base, merged with Reciprocal Rank Fusion. |
| **Deterministic where it matters** | Game maths, budgets and filtering are plain Python. The model writes language; it never does arithmetic. |
| **Guarded output** | A post-generation pipeline removes prompt echoes, bot-speak, fabricated citations and sycophancy. |

How a message is handled, and what she keeps between conversations:
[How Kaia works](docs/03-architecture/how-she-works.md).

## Features

| | |
|:--|:--|
| **Aethelgard** | A persistent turn-based RPG: a 77-floor dungeon, 369 monsters, ten advanced classes, housing, farming, pets, alchemy and fishing. Python computes every roll; Kaia narrates each trip out once, when it ends. [System](docs/ttrpg/aethelgard_system.md) |
| **Art** | `!art` makes Electric Sheep: real flock genomes rendered by [flam3](https://github.com/scottdraves/flam3), picked from your words or repainted in an attached picture's colours. `!art loop` posts a rotating loop. |
| **Music** | `!music on` DJs a live-coded [Strudel](https://codeberg.org/uzu/strudel) set in voice across fourteen genres; `!music records` mixes your own library by key and tempo, with a DJ booth window. |
| **Night shift** | Shortwave and sky: HFGCS Emergency Action Messages, number stations, UVB-76, a local RTL-SDR scanner with a receiver dashboard, the ISS, NASA, space weather and tonight's sky. `!nightshift` opens a panel for all of it. |
| **Social** | A daily news brief, optional Bluesky and X posting, and a Project 1999 forum integration whose every draft waits for a person to approve it. |
| **Dashboard** | A terminal dashboard of load, activity, her cognitive state and retrieval health, plus KAIA // OPS, a read-only web admin view. |

All commands: [`docs/02-user-guide/commands.md`](docs/02-user-guide/commands.md), or `!help` in Discord.

## Quick start

Linux, an NVIDIA GPU with 12 GB of VRAM, Python 3.12 and [Ollama](https://ollama.com).

```bash
git clone https://github.com/Ekco-S64QTN6/Kaiacord.git && cd Kaiacord
python3 -m venv venv && venv/bin/pip install -r requirements.txt

ollama pull gemma3:12b             # chat, narration, vision (GPU)
ollama pull nomic-embed-text-cpu   # retrieval embeddings (CPU)

cp .env.example .env               # DISCORD_TOKEN is the only required value
venv/bin/python3 Kaiacord.py       # --no-gui for headless / systemd
```

Optional features fetch what they need once:

```bash
venv/bin/python3 tools/maintenance/fetch_music_assets.py                                  # !music
venv/bin/python3 tools/maintenance/fetch_radio_assets.py                                  # !radio (~3 GB)
venv/bin/python3 tools/maintenance/fetch_art_flock.py --build-flam3 --count 300 --gate    # !art
```

Settings, the hardware budget and day-to-day maintenance:
[Configuration and operations](docs/02-user-guide/configuration.md).
Full setup, including the optional radio hardware: [Installation](docs/01-getting-started/installation.md).

## Testing

```bash
venv/bin/python3 -m pytest -q -m "not ollama and not gpu and not slow"
```

A passing suite is not proof a feature works: open what it wrote (the file, the database row, the
clip, the message) and check it. [Testing](docs/04-development/testing.md) has the routine.

## Documentation

| | |
|:--|:--|
| **Using it** | [Installation](docs/01-getting-started/installation.md) · [Quick start](docs/01-getting-started/quick-start.md) · [Commands](docs/02-user-guide/commands.md) · [Configuration](docs/02-user-guide/configuration.md) · [Persona](docs/02-user-guide/persona.md) · [News](docs/02-user-guide/news-system.md) · [Social](docs/02-user-guide/social-media.md) · [Forum](docs/02-user-guide/forum-integration.md) · [Dashboard](docs/02-user-guide/dashboard.md) |
| **How it works** | [How Kaia works](docs/03-architecture/how-she-works.md) · [Architecture](docs/03-architecture/overview.md) · [Retrieval](docs/03-architecture/rag-system.md) · [Intelligence layer](docs/03-architecture/intelligence-layer.md) · [GPU](docs/03-architecture/gpu-management.md) · [`utils/`](docs/03-architecture/utils-reference.md) |
| **Aethelgard** | [System](docs/ttrpg/aethelgard_system.md) · [Lore](docs/ttrpg/aethelgard_lore_bible.md) |
| **Working on it** | [Contributing](CONTRIBUTING.md) · [Testing](docs/04-development/testing.md) · [Maintenance](docs/05-maintenance/procedures.md) · [Troubleshooting](docs/06-troubleshooting/common-issues.md) · [Roadmap](docs/ROADMAP.md) |

## License

[MIT](LICENSE). Dependencies are permissively licensed, except three that carry no obligation here:
`browser_cookie3` (LGPL, optional X cookie import), and Strudel (AGPL-3.0) and kiwiclient (partly
GPL), which are fetched at install time and only driven from here. flam3 (GPL) is built and run as
a separate program. Electric Sheep genomes are CC BY-NC 3.0 and credited on every post. The models
are under their own terms: [Gemma](https://ai.google.dev/gemma/terms),
[Nomic Embed](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5).
