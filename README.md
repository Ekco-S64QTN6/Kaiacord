# Kaiacord

Kaia is a Linux-native AI assistant for Discord, powered by Ollama.

## Features
- **Discord Integration**: Connects seamlessly using `discord.py`.
- **Local Inference**: Powered by Ollama (`gemma3:12b`) for private, local processing.
- **Local RAG System**: Remembers information from local text files and PDFs using `llama-index`.
- **Dynamic Memory**: Use `kaia remember <text>` to store new information on the fly.
- **Customizable Persona**: Tailor her personality via `kaia_persona.md`.
- **Message Handling**: Automatically splits long responses into chunks.

## Local RAG System
Kaia uses a Retrieval-Augmented Generation (RAG) system to access local knowledge.
- **Stack**: Built with `llama-index`, `SimpleVectorStore`, and `OllamaEmbedding` (`nomic-embed-text`).
- **Knowledge Base**: Supports `.txt` and `.pdf` files in the `./knowledge_base` folder.
- **Dynamic Memory**: Use `kaia remember <something>` to log info to `user_memories.txt` and re-index immediately.
- **Framing**: Context is presented as "recovered logs" or "memory fragments" to maintain the hacker persona.

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
