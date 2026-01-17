# Kaiacord

Kaia is a Linux-native AI assistant for Discord, powered by Ollama.

## Features
- **Discord Integration**: Connects seamlessly using `discord.py`.
- **Local Inference**: Powered by Ollama (`gemma3:12b`) for private, local processing.
- **Local RAG System**: Remembers information from local text files, PDFs, and Markdown using `llama-index`.
- **Dynamic Memory**: Use `kaia remember <text>` to store new information on the fly.
- **Image Generation**: Use `kaia, draw <prompt>` to generate images locally with FLUX.1-schnell.
- **Idle Quips**: Generates random comments when left alone too long.
- **Customizable Persona**: Tailor her personality via `kaia_persona.md`.
- **Message Handling**: Automatically splits long responses into chunks.
- **Per-User Logging**: Tracks interactions per user for persistent memory.

## Local RAG System
Kaia uses a Retrieval-Augmented Generation (RAG) system to access local knowledge.
- **Stack**: Built with `llama-index`, `SimpleVectorStore`, and `OllamaEmbedding` (`nomic-embed-text`).
- **Knowledge Base**: Supports `.txt`, `.pdf`, and `.md` files in the `./knowledge_base` folder.
- **Dynamic Memory**: Use `kaia remember <something>` to log info to `user_memories.txt` and re-index immediately.
- **Framing**: Context is presented as "recovered logs" or "memory fragments" to maintain the hacker persona.
- **PDF Auto-Conversion**: PDFs that fail to ingest (e.g., context length errors) are automatically converted to Markdown.
- **Corrupt File Quarantine**: Problematic files are moved to `./knowledge_base/corrupt_files/`.

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
- **Knowledge**: Add or remove files in `./knowledge_base` to update her "memory".
