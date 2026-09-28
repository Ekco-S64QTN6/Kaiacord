# Daily News Updater
The Daily News Updater is an automated system that keeps Kaia informed about current events, specifically focusing on tech, cybersecurity, infrastructure, and culture.

## 1. How it Works
The system uses the Gemini API with **Google Search grounding** to generate accurate daily briefs based on real, current news stories.

- **Generation**: `tools/maintenance/update_kaia_news.py` calls the Gemini API (`gemini-2.5-flash`) with Google Search grounding enabled.
- **Grounding**: passes the `google_search` tool, so the brief is written from real search results rather than the model's memory.
- **Ingestion**: The brief is saved to `knowledge_base/news/daily/news_brief_YYYYMMDD.md`.
- **Summarization**: A condensed version is created as `knowledge_base/news/daily/news_summary_YYYYMMDD.md` using the local `gemma3:12b` model. It is the quick reference for `!news` and is deliberately **not** indexed — it would retrieve each day's news twice, once undated.
- **Reindexing**: The script requests a RAG refresh (`rag_utils.request_reindex`), so the brief is searchable within minutes.
- **Retrieval**: news reaches a conversation only when the turn is about news; a turn asking what is *current* is also offered the newest briefs on its topic, and briefs are dated by their filename, not the file's mtime.

## 2. Categories
Kaia supports specific news categories for targeted queries:
- **technology**: AI, software, hardware, and digital infrastructure.
- **politics**: Legislation, elections, and government policy.
- **business**: Markets, economy, and corporate news.
- **security**: Hacks, breaches, vulnerabilities (CVEs), and patches.
- **science**: Research, space, and scientific breakthroughs.
- **culture**: Entertainment, trends, and society.
- **hacker**: APT groups, manifestos, and cyberwarfare.
- **general**: A mix of all the above.

## 3. Usage
```bash
# Generate today's news (skips backfill to conserve API quota)
venv/bin/python3 tools/maintenance/update_kaia_news.py

# Generate with backfill (fills in missing days, uses more API quota)
venv/bin/python3 tools/maintenance/update_kaia_news.py --backfill
```

Without `GEMINI_API_KEY` it stops and says how to file a brief by hand (below).

## 4. Manual Ingestion
If you manually generate a news brief (e.g., via the Gemini web interface), you can ingest it into Kaia's knowledge base using the ingestion tool:

1. Save your manual brief as a `.md`, `.txt`, or `.json` file in the root `news/` folder, `knowledge_base/news/daily/`, or `knowledge_base/news/weekly/`.
2. Name it with a date (e.g., `NEWS_BRIEF: 2026-02-01.md` or `WEEKLY_NEWS_BRIEF: 2026-01-26 to 2026-02-01.md`).
3. Run the ingestion script:
   ```bash
   venv/bin/python3 tools/maintenance/ingest_manual_news.py
   ```
The script will:
- Rename and move the file to the proper format (`news_brief_YYYYMMDD.md` for daily, `weekly_summary_YYYYMMDD.md` for weekly).
- Normalize headers (adding `## ` to category names) for RAG optimization and NewsManager compatibility.
- Generate a condensed summary (for daily briefs) using the local `gemma3:12b` model.
- Trigger a RAG reindex.

## 5. Automation
The running bot refreshes the news itself every 12 hours, as a subprocess (and at startup too
when `startup.news_update` is on; it is off by default). All it needs is `GEMINI_API_KEY` in `.env`; enable billing
on the Google Cloud project for more quota. Without the bot, a cron line does the same:
```bash
0 9 * * * cd /path/to/Kaiacord && venv/bin/python3 tools/maintenance/update_kaia_news.py
```

## 6. API Quota
- **Free tier**: 20 requests/day per model (may hit limits with backfill enabled)
- **Paid tier**: Enable billing at https://aistudio.google.com/ for higher limits
- **Tip**: Skip backfill (default) to conserve quota for today's news only

## 7. Maintenance
The script automatically archives news briefs and summaries older than **14 days** to `knowledge_base/news/archive/` to keep the knowledge base focused.

## 8. `!news`
`!news` answers in the standard embed box: today's headlines, numbered. `!news 3` opens story 3
with its background from earlier briefs, and `!news security` (or any category above) shows one
section. `!news hacking` is accepted for `hacker`.

## 9. Dependencies
- **google-genai**: New Google GenAI SDK with grounding support
- **ollama**: For local summarization with gemma3:12b
