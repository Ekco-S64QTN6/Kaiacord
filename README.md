<h1 align="center">Kaiacord 🤖</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Discord-API-7289DA?style=for-the-badge&logo=discord" />
  <img src="https://img.shields.io/badge/Ollama-Local-FF6B35?style=for-the-badge" />
  <img src="https://img.shields.io/badge/RAG-Enabled-10B981?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Vision-Capable-8A2BE2?style=for-the-badge" />
</p>

<p align="center">
  <strong>A Linux-native, self-hosted AI chatbot for Discord with local inference, memory, and vision capabilities.</strong>
</p>

---

## ✨ Features Overview

### 🤖 Core Intelligence
*   **Local AI Inference** – Powered by Ollama (`gemma3:12b`) for private, offline processing.
*   **Dynamic RAG System** – Remembers information from text files, PDFs, Markdown, and Word documents.
*   **Query Classification** – Automatically detects intent (Identity, Knowledge, Casual) for optimized responses.
*   **Self-Healing System** – Retries failed LLM calls with simplified prompts or reduced context.
*   **Color-Coded Logging** – Beautiful terminal output with high-visibility timestamps and message types.

### 🧠 Advanced Memory & Learning
*   **Deep User Profiling** – Generates structured user profiles analyzing topics, style, and interaction patterns.
*   **Relationship Tracking** – Visualizes trust and relationship evolution over time.
*   **Personalized Memory** – Prioritizes user-specific history and preferences during interactions.
*   **Incremental Indexing** – Only processes new/modified files for significantly faster boot times.
*   **Tail-Indexing for Logs** – Efficiently indexes only new content in log files using byte offsets.

### 🛡️ Hallucination Prevention (Kaia 2.5+)
| Feature | Protection |
| :--- | :--- |
| **Hallucination Detector** | Real-time detection of known hallucination patterns (Juanita, Deane, etc.). |
| **Emergency Filter** | Surgical removal of hallucinated lines before sending or logging. |
| **Feedback Loop Protection** | Prevents hallucinated content from being logged or cached. |
| **Nuclear Reset** | Automated process to purge persistent hallucinations from all systems. |
| **Strict Identity Filtering** | Enforces source-specific retrieval for identity-related queries. |

### 🎨 Multimodal Capabilities
*   **Image Generation** – `kaia draw <prompt>` generates images locally with FLUX.1-schnell.
*   **Image Vision & Analysis** – Upload images for analysis using `llama3.2-vision`.
*   **Automatic VRAM Management** – Unloads Ollama models during image generation to prevent OOM.

### ⚡ Performance & Architecture
*   **Non-Blocking RAG** – Dedicated thread pool keeps the Discord event loop responsive.
*   **Concurrency Control** – Semaphore-based image generation prevents VRAM conflicts.
*   **Circuit Breakers** – Gracefully handles failures in external services (e.g., PDF conversion).
*   **Improved Semantic Cache** – Date-aware caching with keyword blacklisting to prevent stale data.

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/YOUR_USERNAME/Kaiacord.git
cd Kaiacord
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Ollama Models
```bash
ollama pull gemma3:12b
ollama pull nomic-embed-text
ollama pull llama3.2-vision:11b
```

### 3. Configure Environment
Create a `.env` file in the root directory:
```env
DISCORD_TOKEN=your_discord_token_here
GEMINI_API_KEY=your_gemini_api_key_here  # Optional: for daily news updater
```

### 4. Launch
```bash
python Kaiacord.py
```

---

## 📁 Project Structure
```text
Kaiacord/
├── Kaiacord.py              # Main bot entry point
├── kaia_persona.md          # Customizable personality & backstory
├── knowledge_base/          # Local knowledge storage
│   ├── user_logs/           # Per-user interaction logs
│   └── corrupt_files/       # Quarantined problematic files
├── tools/                   # Maintenance & diagnostics
│   ├── nuclear_reset.py     # Complete system purge
│   ├── find_contamination.py # Hallucination detection
│   └── update_kaia_news.py  # Daily news updater (RAG-optimized)
├── test_scripts/           # Core test utilities & verification
└── docs/                   # Detailed documentation
    ├── HALLUCINATION_FIXES.md
    ├── INTELLIGENCE_LAYER.md
    └── DAILY_NEWS_UPDATER.md
```

---

## 🛠️ Usage Examples

### 💬 Basic Interaction
> **User**: @kaia What's the weather like?
>
> **Kaia**: ```hiccups in the cloud layer. looks like rain.```

> **User**: @kaia remember that I prefer dark mode
>
> **Kaia**: ```Logged it.```

### 🖼️ Image Generation & Analysis
> **User**: kaia draw a cyberpunk cityscape
>
> **Kaia**: ```flickering the screen. give me a second.``` *(Sends FLUX-generated image)*

> **User**: *(Uploads image)* kaia what do you see here?
>
> **Kaia**: ```looking... looks like a cluster of server racks. messy cable management.```

---

## 🔧 Customization

### Persona Customization
Edit `kaia_persona.md` to define her personality, backstory, and behavior patterns. She is designed to be blunt, grounded, and technically proficient.

### Knowledge Base
Add files to `./knowledge_base/` in supported formats:
*   `.txt`, `.md`, `.pdf`, `.docx`
Kaia will automatically index them and use them as context for her responses.

---

## 🩺 Maintenance & Diagnostics

| Tool | Purpose |
| :--- | :--- |
| **nuclear_reset.py** | Complete system purge of hallucinations and corrupted data. |
| **find_contamination.py** | Diagnostic tool for identifying fictional elements in logs. |
| **update_kaia_news.py** | Automated daily news brief generator with RAG-optimized formatting. |

Run maintenance scripts from the `tools/` directory.

---

## 📈 Roadmap
- [x] **Kaia 2.4** – User profiling & relationship tracking
- [x] **Kaia 2.5** – Advanced hallucination prevention & Nuclear Reset
- [x] **Kaia 2.5.1** – RAG-optimized Daily News Updater
- [ ] **Kaia 2.6** – Multi-modal RAG (images in knowledge base)
- [ ] **Kaia 2.7** – Plugin system for extended functionality

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

---
