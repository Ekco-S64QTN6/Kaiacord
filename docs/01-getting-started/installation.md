# Installation Guide

Complete installation guide for Kaiacord.

## Prerequisites

### Required
- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Arch, etc.)
- **Python**: 3.12 (the project's venv; `Kaiacord.py` re-launches itself in it)
- **GPU**: NVIDIA with 12 GB of VRAM (RTX 3060 or better). `gemma3:12b` takes about 9.5 GiB at
  the default 16,384-token context, and the desktop needs its share of the rest; an 8 GB card
  cannot hold it.
- **Disk Space**: about 10 GB for the models, plus ~3 GB if you fetch the radio assets
- **RAM**: 16GB+ system RAM (32GB recommended)
- **Discord**: Bot token ([Get one here](https://discord.com/developers/applications))

### Optional
- **Gemini API Key**: For news generation feature
- **SSD Storage**: Recommended for faster model loading
- **ffmpeg, pactl**: `!music` and live radio in voice; `venv/bin/python3 tools/maintenance/fetch_music_assets.py` and `fetch_radio_assets.py` fetch Strudel, kiwiclient and faster-whisper
- **An RTL-SDR dongle** and the `rtl-sdr` package (librtlsdr, `rtl_fm`): the local `!scanner`. Name your local repeaters and nets under `radio.local` in `kaia.yaml`

---

## Step 1: System Dependencies

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

### Arch Linux
```bash
sudo pacman -S python python-pip git
```

---

## Step 2: Install Ollama

Ollama is required for local AI inference.

```bash
# Download and install
curl -fsSL https://ollama.ai/install.sh | sh

# Verify installation
ollama --version

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama  # Auto-start on boot
```

---

## Step 3: Clone Repository

```bash
git clone https://github.com/Ekco-S64QTN6/Kaiacord.git
cd Kaiacord
```

---

## Step 4: Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

`discord.py` 2.7 and `davey` are required, not optional: Discord refuses any voice connection
without its DAVE end-to-end encryption, which older discord.py lacks.

---

## Step 5: Pull AI Models

**About 9 GB to download.**

```bash
# Chat, narration and vision (~9.5 GiB of VRAM once loaded)
ollama pull gemma3:12b

# Embedding model (runs on CPU)
ollama pull nomic-embed-text-cpu
```

Two models, and only two. A `gemma2:2b` classification model used to be listed
here; it was removed in September 2026 because its verdict was never read. If you
pulled it for an earlier version, `ollama rm gemma2:2b` reclaims 1.6 GB.

---

## Step 6: Configuration

### Option A: Quick Setup (.env)
```bash
cp .env.example .env
# then set DISCORD_TOKEN; everything else is optional
```

`GEMINI_API_KEY` is used only for the daily news brief, and `NASA_API_KEY` lifts `!nasa` and
`!earth` off NASA's shared demo key. Bluesky, X and the forum each need their credentials
**and** their `enabled` flag in `config/kaia.yaml`.

### Option B: Advanced Setup (YAML)
```bash
# Edit user overrides (do NOT copy the entire default_config.yaml)
# Only add the settings you want to change
nano config/kaia.yaml
```

**See**: `config/kaia.yaml` for available settings (override `config/default_config.yaml`)

---

## Step 7: Verify Installation

```bash
venv/bin/python3 tools/maintenance/health_check.py
```

It prints one line per check — the venv and packages, the GPU, Ollama and each model, the
Discord token, the knowledge base, directory permissions — with ✅ or ❌, then any warnings and
errors. Fix every ❌ before the first run.

---

## Step 8: First Run

```bash
venv/bin/python3 Kaiacord.py            # with the terminal dashboard
venv/bin/python3 Kaiacord.py --no-gui   # headless
```

The first boot loads `gemma3:12b` onto the GPU, then comes online, then indexes the knowledge
base in the background — the first full index of a large corpus takes a while on the CPU.

---

## Step 9: Test in Discord

In your Discord server, say `kaia` or `status`: she answers with a short, casual word about her
day. `!help` lists the commands.

---

## Troubleshooting Installation

### Ollama Not Found
```bash
# Check if Ollama is running
ollama list

# If not, start the service
sudo systemctl start ollama
```

### GPU Not Detected
```bash
# Check NVIDIA driver
nvidia-smi

# If not installed, install NVIDIA drivers
sudo ubuntu-drivers autoinstall  # Ubuntu
sudo pacman -S nvidia nvidia-utils  # Arch
```

### Module Import Errors
```bash
# Run with the venv's interpreter, not the system one
venv/bin/python3 tools/maintenance/health_check.py

# Reinstall dependencies into the venv
venv/bin/pip install -r requirements.txt --force-reinstall
```

A package installed with the system `pip` lands outside the venv and fixes nothing; a
`No module named …` deep inside a subsystem usually means the wrong interpreter.

### Models Not Loading
```bash
# Verify models are pulled
ollama list

# Re-pull if needed
ollama pull gemma3:12b
```

---

## Next Steps

1. **[Quick Start Guide](quick-start.md)**
2. **Configuration** ([../config/kaia.yaml](../../config/kaia.yaml))
3. **Command Reference** ([../02-user-guide/commands.md](../02-user-guide/commands.md))

---

## Advanced Installation Options

### Docker
```bash
# Not currently supported — Kaiacord requires direct GPU access via Ollama
```

### Systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/kaiacord.service
```

```ini
[Unit]
Description=Kaiacord Discord Bot
After=network.target ollama.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/Kaiacord
Environment="PATH=/home/your_username/Kaiacord/venv/bin"
ExecStart=/home/your_username/Kaiacord/venv/bin/python Kaiacord.py --no-gui
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable kaiacord
sudo systemctl start kaiacord

# Check status
sudo systemctl status kaiacord
```

---

## Uninstallation

```bash
# Stop bot
# Ctrl+C or:
sudo systemctl stop kaiacord

# Remove repository
cd ..
rm -rf Kaiacord

# Remove Ollama (optional)
sudo systemctl stop ollama
sudo systemctl disable ollama
sudo rm /usr/local/bin/ollama
```

---

<p align="center">
  <sub>Installation complete? Head to <a href="quick-start.md">Quick Start</a>!</sub>
</p>
