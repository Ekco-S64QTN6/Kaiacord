# Kaiacord

Kaia is a Linux-native AI assistant for Discord, powered by Ollama.

## Features
- **Discord Integration**: Connects seamlessly using `discord.py`.
- **Local Inference**: Powered by Ollama (`gemma3:12b`) for private, local processing.
- **Local RAG System**: Remembers information from local text files, PDFs, Markdown, and Word documents using `llama-index`.
- **Dynamic Memory**: Use `kaia remember <text>` to store new information directly into her interaction logs.
- **Image Generation**: Use `kaia, draw <prompt>` or `kaia draw <prompt>` to generate images locally with FLUX.1-schnell. Includes automatic VRAM management by unloading Ollama models.
- **Image Vision & Analysis**: Upload images with "kaia" mention for her to analyze and comment on them (uses llama3.2-vision).
- **Idle Quips**: Generates random comments when left alone too long (max 3 consecutive).
- **Customizable Persona**: Tailor her personality via `kaia_persona.md`.
- **Message Handling**: Automatically splits long responses into chunks.
- **Per-User Logging**: Tracks interactions per user for persistent memory and ingestion.
- **Personalized Memory**: Automatically retrieves and prioritizes a user's specific history and preferences (like pronouns) during interactions.
- **Color-Coded Logging System**: Enhanced terminal output with high-visibility timestamps, success markers, and color-coded message types (actions, users, responses, errors).
- **RAG Context Visualization**: Displays retrieved context nodes in a structured table for easier debugging and transparency.

## Local RAG System
Kaia uses a Retrieval-Augmented Generation (RAG) system to access local knowledge.
- **Stack**: Built with `llama-index`, `SimpleVectorStore`, and `OllamaEmbedding` (`nomic-embed-text`).
- **Knowledge Base**: Supports `.txt`, `.pdf`, `.md`, and `.docx` files in the `./knowledge_base` folder.
- **Recursive Scanning**: Automatically scans all subdirectories (e.g., `user_logs/`) for ingestion.
- **Tail-Indexing for Logs**: Efficiently indexes only new content in log files using byte offsets.
- **Incremental Indexing**: Only processes new or modified files for significantly faster boot times.
- **Lazy Persistence**: RAG index is persisted periodically and on shutdown to maximize responsiveness.
- **Dynamic Memory**: Use `kaia remember <something>` to log info directly to her interaction logs for immediate re-indexing.
- **Metadata-First Retrieval**: Strictly prioritizes a user's specific history and preferences using metadata filters.
- **Self-Identity Retrieval**: Explicitly indexes `kaia_persona.md` and her own logs to provide accurate answers about her own identity.
- **Garbage Text Filter**: Automatically filters out corrupted or low-quality text fragments (e.g., from bad PDF extractions) during retrieval.
- **Framing**: Context is presented as "recovered logs" or "internal memory recovery" to maintain the hacker persona.
- **PDF & DOCX Auto-Conversion**: PDFs and Word documents are automatically converted to Markdown for more reliable retrieval.
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
   ollama pull llama3.2-vision:11b  # For image analysis feature
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

## Testing
All test scripts and diagnostic tools are located in the `test_scripts/` directory.

## Customization
- **Persona**: Modify `kaia_persona.md` to change her personality.
- **Knowledge**: Add or remove files in `./knowledge_base` to update her "memory".
