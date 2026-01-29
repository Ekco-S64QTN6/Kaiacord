# Quick Start Guide

Get Kaia up and running in 5 minutes.

## Prerequisites Check

Before starting, ensure you have:
- ✅ Linux system
- ✅ Python 3.9+
- ✅ NVIDIA GPU (8GB+ VRAM)
- ✅ Discord bot token
- ✅ 30GB free disk space

**Don't have these?** → [Full Installation Guide](installation.md)

---

## 1-Minute Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/Kaiacord.git && cd Kaiacord

# Install Python deps
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Pull AI models (this takes time!)
ollama pull gemma3:12b
ollama pull llama3.2-vision:11b
ollama pull nomic-embed-text

# Configure
echo "DISCORD_TOKEN=your_token_here" > .env

# Launch!
python Kaiacord.py
```

---

## Verify It Works

### Test 1: Health Check
```bash
python tools/maintenance/health_check.py
```

Expected: All ✅ green checks

### Test 2: Discord Interaction
In Discord

:
```
@kaia status
```

Expected response:
```
online. gpu loaded. all systems nominal.
```

### Test 3: Chat
```
@kaia what's Python?
```

Expected: Concise, lowercase response about Python

---

## Common First-Run Issues

### Issue: "Ollama not found"
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start service
sudo systemctl start ollama
```

### Issue: "GPU not detected"
```bash
# Check GPU
nvidia-smi

# If missing, install drivers
sudo ubuntu-drivers autoinstall  # Ubuntu
sudo pacman -S nvidia nvidia-utils  # Arch
```

### Issue: "Discord token invalid"
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create application → Bot → Copy token
3. Update `.env` with **full token**

---

## Next Steps

### Learn the Basics
- **[Basic Usage Guide](../02-user-guide/basic-usage.md)** - Commands and features
- **[Dashboard Guide](../02-user-guide/dashboard.md)** - Understanding the UI
- **[Configuration Guide](configuration.md)** - Customization

### Try Advanced Features
- **Image Generation**: `kaia draw cyberpunk city`
- **Vision Analysis**: Upload image + `@kaia what do you see?`
- **News**: `!news technology`

### Customize
- **Persona**: Edit `config/kaia_persona.md`
- **Knowledge Base**: Add files to `knowledge_base/`
- **Settings**: Edit `config/kaia.yaml`

---

## Cheatsheet

| Command | Action |
|:--------|:-------|
| `@kaia status` | Check bot health |
| `@kaia [question]` | Ask anything |
| `kaia draw [prompt]` | Generate image |
| `!news [category]` | Get news briefs |
| Upload image → `@kaia what?` | Vision analysis |

---

<p align="center">
  <sub>🎉 All set! Join our community or <a href="../02-user-guide/basic-usage.md">learn more</a>!</sub>
</p>
