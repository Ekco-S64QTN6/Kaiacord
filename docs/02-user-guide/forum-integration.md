# 🏟️ Forum Integration & Archaeology

Kaiacord features a robust VBulletin 3.x client designed for deep archival scraping, community interaction, and knowledge synthesis.

## ⚙️ Configuration

Forum settings are managed in `config/kaia.yaml`:

```yaml
forum:
  enabled: true
  base_url: "https://project1999.com/forums"
  forum_id: 30       # Default subforum (e.g., Off Topic)
  username: "Kaia"
  password: "${FORUM_PASSWORD}" # Loaded from .env
  
  # Safety: Kaia will only auto-reply in these threads
  allowed_threads:
    - 446859 # Intro Thread
```

Add your password to `.env`:
```env
FORUM_PASSWORD=your_secure_password
```

---

## 🛠️ Features

### 1. Multi-Page Deep Scraping
Kaia doesn't just skim the surface. She can dive back through dozens of pages to capture the full context of a discussion.
- **Scrape Limit**: Configurable post count (default 50).
- **Page Diving**: Automatically iterates backwards through thread pages until the post limit is reached.

### 2. Unified Identity Linking
Kaia can bridge the gap between platforms. By linking a Discord ID to a Forum UID, she creates a unified "personality dossier."
- **Command**: `!forum link <forum_uid>`
- **Effect**: Merges scraping data from both platforms into a single RAG-indexed user profile.

### 3. Technical Knowledge Synthesis
Kaia acts as a digital archaeologist, distilling chaotic forum threads into structured knowledge.
- **Logic**: `tools/social/synthesize_technical_knowledge.py`
- **Workflow**:
    1. Scrape a technical subforum (e.g., Forum 40).
    2. Convert threads to clean Markdown.
    3. Use the LLM to extract **Problem/Solution** pairs.
    4. Consolidate into a high-density **Technical Cheat Sheet**.

---

## 🛡️ Safety & Protocols

### Thread Allowlisting
To prevent Kaia from "leaking" into sensitive or inappropriate discussions, she uses a strict **Thread Allowlist**. She will monitor the whole forum but only active the auto-responder in threads listed in `forum.allowed_threads`.

### Persona Consistency
The forum client uses the same `kaia_persona.md` as the Discord bot, ensuring her tone (all-lowercase, blunt, technical) remains consistent across platforms.

### Automated Introductions
When entering a new subforum, use `tools/development/generate_intro_post.py` to draft a context-aware introduction that aligns with the current community state and Kaia's project goals.
