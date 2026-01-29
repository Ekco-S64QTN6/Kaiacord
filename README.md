<h1 align="center">Kaiacord 🤖</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Discord-API-7289DA?style=for-the-badge&logo=discord" />
  <img src="https://img.shields.io/badge/Ollama-Local-FF6B35?style=for-the-badge" />
  <img src="https://img.shields.io/badge/RAG-Enabled-10B981?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Vision-Capable-8A2BE2?style=for-the-badge" />
  <img src="https://img.shields.io/badge/GPU-12GB%20VRAM-F59E0B?style=for-the-badge&logo=nvidia" />
</p>

<p align="center">
  <strong>A Linux-native, self-hosted AI chatbot for Discord with local inference, memory, vision, and image generation.</strong>
</p>

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- **Python** 3.9+
- **GPU** with 8GB+ VRAM (12GB recommended for RTX 3060)
- **Discord Bot Token** ([Get one here](https://discord.com/developers/applications))
- **Ollama** installed ([Download](https://ollama.ai))

### Installation
```bash
# 1. Clone and setup
git clone https://github.com/YOUR_USERNAME/Kaiacord.git
cd Kaiacord
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Pull AI models (this will take a while)
ollama pull gemma3:12b           # Chat model (8GB)
ollama pull llama3.2-vision:11b  # Vision model (7.5GB)
ollama pull nomic-embed-text     # Embedding model

# 3. Configure
cp .env.example .env  # Create from example, or:
echo "DISCORD_TOKEN=your_token_here" > .env
echo "GEMINI_API_KEY=your_key_here" >> .env  # Optional: for news generation

# 4. Launch!
python Kaiacord.py
```

**First message**: `@kaia status` in Discord to verify it's working!

---

## 🎉 What's New in v2.0

**v2.0** brings **major stability and architecture improvements**:

✅ **Critical Bugs Fixed**: `stats_poller` NameError, circular logging dependencies, GPU memory issues  
✅ **Modular Architecture**: Organized `bot/managers/` structure (config, state, rate limiting)  
✅ **Unified GPU Manager**: Priority-based VRAM reservation with automatic preemption  
✅ **VRAM Management**: Chat model unloads before vision/image tasks (12GB GPU support)  
✅ **Exception Hierarchy**: User-friendly error messages and comprehensive error handling  
✅ **YAML Configuration**: Hierarchical config with migration from `.env`  
✅ **Comprehensive Testing**: Unit, integration, and performance test suites  
✅ **100% Backward Compatible**: Existing setups work without changes  
✅ **Complete Documentation**: Architecture, migration, troubleshooting, and VRAM guides  

**Code Quality**: Reduced from 2390 → 2260 lines (target: <1000)  
**Test Coverage**: 12/12 tests passing (100%)  

**Upgrade Guide**: See [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md)

---

## ✨ Features

| Category | Features | Status |
|:---------|:---------|:-------|
| **🤖 Core AI** | Local Inference (Ollama), Multi-Model Support (`gemma3:12b`) | ✅ |
| **🧠 Memory** | RAG with File Indexing, User Profiles, Semantic Cache | ✅ |
| **👁️ Vision** | Image Analysis (`llama3.2-vision`), Object Detection, Text Extraction | ✅ |
| **🎨 Generation** | FLUX Image Generation (`flux.1-schnell-4bit`), Prompt Refinement | ✅ |
| **📊 Interface** | Curses Dashboard (btop-style), Discord Bot, Color-Coded Logging | ✅ |
| **🎯 Intelligence** | Query Classification, Personalization, Hallucination Prevention | ✅ |
| **⚡ Performance** | VRAM Management (12GB), Model Unload/Reload, Rate Limiting | ✅ |
| **📰 News** | Daily Tech Briefs, Manual Retrieval (`!news technology`), 14-day Retention, Archive System | ✅ |

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Discord Bot                          │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    ┌────▼─────┐          ┌─────▼─────┐
    │ Handlers │          │ Commands  │
    │ (Events) │          │  (!news)  │
    └────┬─────┘          └─────┬─────┘
         │                      │
         └──────────┬───────────┘
                    │
            ┌───────▼────────┐
            │   Services     │
            │ ┌────────────┐ │
            │ │ RAG System │ │◄─── knowledge_base/
            │ ├────────────┤ │
            │ │   Vision   │ │◄─── llama3.2-vision
            │ ├────────────┤ │
            │ │ Image Gen  │ │◄─── flux.1-schnell
            │ └────────────┘ │
            └───────┬────────┘
                    │
            ┌───────▼────────┐
            │    Managers    │
            │ ┌────────────┐ │
            │ │   Config   │ │◄─── config/kaia.yaml
            │ ├────────────┤ │
            │ │ GPU Memory │ │◄─── VRAM Reservation
            │ ├────────────┤ │
            │ │   State    │ │◄─── storage/
            │ └────────────┘ │
            └───────┬────────┘
                    │
            ┌───────▼────────┐
            │  Utils Layer   │
            │  (kaia_*.py)   │
            └────────────────┘
```

**Key Principle**: Chat model (8GB) unloads before vision (7.5GB) or image gen (6-8GB) to prevent VRAM overflow on 12GB GPUs.

---

## 📋 Usage Examples

### 💬 Basic Chat
```
User: @kaia what's Python?
Kaia: programming language. general purpose. readable syntax. popular for automation and data work.

User: @kaia remember I'm working on a Discord bot
Kaia: logged it.
```

### 🎨 Image Generation
```
User: kaia draw a cyberpunk cityscape at night
Kaia: flickering the screen. give me a second.
[Sends FLUX-generated image]
```

### 👁️ Vision Analysis
```
User: [Uploads server rack image] kaia what do you see?
Kaia: looking...
Kaia: server racks. messy cable management. looks like a data center. couple switches on the left.
```

### 📰 News Retrieval
```
User: !news
Kaia: 📰 **Technology News**

1. **Azure/AWS/GCP:** AWS US-EAST-1 experienced severe DNS failure...
2. **Models:** Meta released Llama 4.5 with 2.5 trillion parameters...
...

---
**Other categories:** `!news security` `!news hacking` `!news politics` ...

User: !news security
Kaia: 📰 **Security News**
[Security briefings and vulnerabilities]
```

**Categories**: `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

**Features**:
- Auto-generates daily on boot (requires `GEMINI_API_KEY`)
- 14-day retention → Auto-archives to `knowledge_base/news/archive/`
- Weekly summaries from archived news

### 📊 Dashboard
```bash
python Kaiacord.py  # Launches curses dashboard

# Dashboard shows:
# - Real-time GPU memory usage
# - Active model (gemma3:12b / llama3.2-vision)
# - Live logs with color coding
# - System stats (CPU, RAM, requests/min)
```

---

## ⚙️ Configuration

### Quick Config (`.env`)
```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_api_key  # Optional: for news generation
```

### Advanced Config (`config/kaia.yaml`)
```yaml
# Override defaults hierarchically
discord:
  blacklisted_channels: "general,announcements"

models:
  chat: "gemma3:12b"
  vision: "llama3.2-vision:11b"

gpu:
  image_gen_min_vram_gb: 8.0  # Minimum VRAM for image gen

performance:
  max_memory_messages: 30
  requests_per_minute: 30
```

**Migration**: Use `python scripts/migrate_config.py` to convert `.env` → `kaia.yaml`

---

## 🎛️ Advanced Features

### Custom Persona
Edit `config/kaia_persona.md` to customize personality:
```markdown
# Kaia's Persona

You are Kaia, a blunt, grounded AI with technical expertise.
- Use lowercase for casual tone
- Be direct and concise
- Focus on facts over fluff
```

### Knowledge Base Management
```bash
# Add documents (auto-indexed)
cp my_docs.pdf knowledge_base/
# Kaia automatically detects and indexes new files

# Force re-index
python tools/maintenance/refresh_rag_index.py
```

### GPU Management (12GB VRAM)
Kaia automatically manages VRAM:
1. **Chat**: gemma3:12b loaded (8GB)
2. **Image/Vision**: Unload chat → Load vision/flux → Process → Reload chat
3. **Monitor**: `watch -n 1 nvidia-smi` to see VRAM usage

**See**: [`docs/VRAM_MANAGEMENT.md`](docs/VRAM_MANAGEMENT.md) for details

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific suites
pytest tests/unit/ -v           # Fast unit tests
pytest tests/integration/ -v    # End-to-end tests
pytest tests/verification/ -v   # System checks

# Health check
python tools/health_check.py
```

---

## 🛠️ Troubleshooting

### Common Issues

| Issue | Solution |
|:------|:---------|
| **Vision timeout (5+ min)** | Model load timeout. Increase timeout in `utils/gpu_manager.py:118` to 90s |
| **CUDA Out of Memory** | Chat model not unloading. Check logs for "Unloading chat model" |
| **stats_poller NameError** | Fixed in v2.0. Update to latest version |
| **!news not working** | Fixed in v2.0. Use `!news technology`, `!news security`, etc. |
| **Dashboard crashes** | Try `KAIA_DASHBOARD=simple python Kaiacord.py` for fallback mode |

**Full Guide**: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

---

## 📁 Project Structure

```
Kaiacord/
├── Kaiacord.py              # Main bot entry point
├── bot/                     # NEW: Modular bot package
│   ├── managers/            # Configuration, state, GPU, rate limiting
│   ├── handlers/            # Message, command, event handlers (WIP)
│   ├── services/            # RAG, vision, image services (WIP)
│   └── exceptions.py        # Custom exception hierarchy
├── utils/                   # Core utilities
│   ├── kaia_rag.py          # RAG system
│   ├── kaia_vision.py       # Vision analysis
│   ├── kaia_image.py        # Image generation
│   ├── kaia_news.py         # News manager
│   ├── gpu_manager.py       # GPU/VRAM management
│   ├── kaia_intelligence.py # Query classification
│   └── btop_dashboard_v2.py # Curses dashboard
├── config/                  # Configuration
│   ├── kaia_persona.md      # Customizable personality
│   ├── default_config.yaml  # Default settings
│   └── kaia.yaml            # User overrides
├── knowledge_base/          # RAG knowledge storage
│   ├── news/daily/          # Daily news briefs
│   ├── user_logs/           # Interaction logs
│   └── user_profiles/       # Generated profiles
├── storage/                 # Persistent data
│   └── semantic_cache.json  # Response cache
├── tests/                   # Test suites
│   ├── unit/                # Fast, isolated tests
│   ├── integration/         # End-to-end tests
│   └── verification/        # System checks
├── tools/                   # Utilities
│   ├── maintenance/         # Regular maintenance
│   ├── diagnostics/         # System diagnostics
│   ├── recovery/            # Emergency recovery
│   └── health_check.py      # System validation
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # System architecture
│   ├── VRAM_MANAGEMENT.md   # GPU memory guide
│   └── [more guides]
└── logs/                    # System logs
```

---

## 📚 Documentation

### 🎯 Essentials
- **[README.md](README.md)** - This file (you are here!)
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Upgrading from v1.0 → v2.0
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues & solutions

### 🏗️ Technical
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design & data flows
- **[docs/VRAM_MANAGEMENT.md](docs/VRAM_MANAGEMENT.md)** - GPU memory for RTX 3060 (12GB)
- **[docs/VISION_FEATURE.md](docs/VISION_FEATURE.md)** - Vision system details
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** - Testing infrastructure

### 🔧 Maintenance
- **[tools/README.md](tools/README.md)** - Maintenance tools reference
- **[docs/maintenance.md](docs/maintenance.md)** - Backup & update procedures

---

## 🤝 Contributing

We welcome contributions! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`pytest tests/ -v`)
4. Commit changes (`git commit -m 'Add amazing feature'`)
5. Push to branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

**Code Style**: Follow PEP 8, use type hints, add docstrings

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ for local AI enthusiasts | GPU-optimized for RTX 3060 12GB</sub>
</p>
