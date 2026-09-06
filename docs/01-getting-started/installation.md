# Installation Guide

Complete installation guide for Kaiacord v2.0.

## Prerequisites

### Required
- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Arch, etc.)
- **Python**: 3.12 or higher
- **GPU**: NVIDIA GPU with 8GB+ VRAM (12GB recommended)
  - RTX 3060 (12GB) - Recommended ✅
  - RTX 3070 (8GB) - Works but tight on VRAM
  - RTX 3080+ (10GB+) - Excellent
- **Disk Space**: 30GB+ for models
- **RAM**: 16GB+ system RAM (32GB recommended)
- **Discord**: Bot token ([Get one here](https://discord.com/developers/applications))

### Optional
- **Gemini API Key**: For news generation feature
- **SSD Storage**: Recommended for faster model loading

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
git clone https://github.com/YOUR_USERNAME/Kaiacord.git
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

---

## Step 5: Pull AI Models

**This will download ~20GB of models. Ensure you have space and bandwidth.**

```bash
# Chat model (~7GB VRAM)
ollama pull gemma3:12b

# Classification model (runs on CPU)
ollama pull gemma2:2b

# Embedding model (runs on CPU)
ollama pull nomic-embed-text-cpu
```

---

## Step 6: Configuration

### Option A: Quick Setup (.env)
```bash
# Create .env file
cat > .env << EOF
DISCORD_TOKEN=your_discord_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here  # Optional
EOF
```

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
# Run health check
python tools/maintenance/health_check.py
```

Expected output:
```
✅ Ollama server: ONLINE
✅ gemma3:12b: Found
✅ gemma2:2b: Found
✅ nomic-embed-text-cpu: Found
✅ GPU: NVIDIA RTX 3060 (12GB)
✅ Knowledge base: Accessible
✅ Configuration: Valid
```

---

## Step 8: First Run

```bash
# Start Kaiacord
python Kaiacord.py
```

You should see:
```
[INFO] 🤖 Kaia is online!
[INFO] 📊 Dashboard started (curses mode)
[INFO] 🟢 Ollama: ONLINE
```

---

## Step 9: Test in Discord

In your Discord server:
```
@kaia status
```

Expected response:
```
online. gpu loaded. all systems nominal.
```

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
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

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
ExecStart=/home/your_username/Kaiacord/venv/bin/python Kaiacord.py
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
