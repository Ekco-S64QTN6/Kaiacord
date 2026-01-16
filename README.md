# Kaiacord

Kaia is a Linux-native AI assistant for Discord, powered by Ollama.

## Features
- Integrates with Discord using `discord.py`.
- Uses Ollama for local LLM inference (`gemma3:12b`).
- **Local RAG System**: Remembers information from local text files using `llama-index`.
- Customizable persona via `kaia_persona.md`.
- Handles long messages by splitting them into chunks.

## Local RAG System
Kaia uses a Retrieval-Augmented Generation (RAG) system to access local knowledge.
- **Stack**: `llama-index` with `SimpleVectorStore` and `OllamaEmbedding` (`nomic-embed-text`).
- **Knowledge Base**: Place `.txt` files in the `./knowledge_base` folder.
- **Framing**: Retrieved info is presented as "recovered logs" or "memory fragments" to maintain Kaia's hacker persona.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Kaiacord.git
   cd Kaiacord
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ensure Ollama models are available:**
   ```bash
   ollama pull gemma3:12b
   ollama pull nomic-embed-text
   ```

5. **Configure environment variables:**
   Create a `.env` file in the root directory and add your Discord token:
   ```env
   DISCORD_TOKEN=your_discord_token_here
   ```

6. **Run the bot:**
   ```bash
   python Kaiacord.py
   ```

## Customization
- **Persona**: Modify `kaia_persona.md` to change her personality.
- **Knowledge**: Add or remove text files in `./knowledge_base` to update her "memory".
