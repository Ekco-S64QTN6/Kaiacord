# Quick Start Guide

Get Kaia up and running in 5 minutes.

## Prerequisites Check

Before starting, ensure you have:
- ✅ Linux system
- ✅ Python 3.12+
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
ollama pull gemma2:2b
ollama pull nomic-embed-text-cpu

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
In Discord:
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

### Issue: "Shard ID None is requesting privileged intents"
Kaia needs access to message content and server members to function correctly.
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application → Go to the **Bot** tab
3. Scroll down to **Privileged Gateway Intents**
4. Toggle ON **Presence Intent**, **Server Members Intent**, and **Message Content Intent**
5. Save changes and restart the bot

---

## Next Steps

### Learn the Basics
- **[Command Reference](../02-user-guide/commands.md)** — All available commands
- **[Dashboard Guide](../02-user-guide/dashboard.md)** — Understanding the curses UI

### Try Features
- **Art**: `!art` to generate fractal flame artwork
- **RPG**: `!rpg` to play the Aethelgard TTRPG
- **News**: `!news technology`
- **Social**: Set up [Bluesky & X](../02-user-guide/social-media.md) cross-posting

### Customize
- **Persona**: Edit `knowledge_base/kaia_persona.md`
- **Knowledge Base**: Add files to `knowledge_base/`
- **Settings**: Edit `config/kaia.yaml`

---

## Cheatsheet

| Command | Action |
|:--------|:-------|
| `@kaia [question]` | Ask anything |
| `!scores` | Gamified memory analytics & affinity leaderboards |
| `!art` | Generate fractal flame art |
| `!rpg` | Open the TTRPG HUD |
| `!news [category]` | Get news briefs |
