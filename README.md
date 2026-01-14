# Kaiacord

Kaia is a Linux-native AI assistant for Discord, powered by Ollama.

## Features
- Integrates with Discord using `discord.py`.
- Uses Ollama for local LLM inference.
- Customizable persona via `kaia_persona.md`.
- Handles long messages by splitting them into chunks.

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

4. **Configure environment variables:**
   Create a `.env` file in the root directory and add your Discord token:
   ```env
   DISCORD_TOKEN=your_discord_token_here
   ```

5. **Run the bot:**
   ```bash
   python Kaiacord.py
   ```

## Customization
You can modify the bot's personality by editing `kaia_persona.md`.
