# Daily News Updater
The Daily News Updater is an automated system that keeps Kaia informed about current events, specifically focusing on tech, cybersecurity, infrastructure, and culture.

## 1. How it Works
The system uses the Gemini API with **Google Search grounding** to generate accurate daily briefs based on real, current news stories.

- **Generation**: `tools/maintenance/update_kaia_news.py` calls the Gemini API (`gemini-2.0-flash`) with Google Search grounding enabled.
- **Grounding**: Uses `types.Tool(google_search=types.GoogleSearch())` to pull real news from Google Search, preventing hallucinated stories.
- **Ingestion**: The brief is saved to `knowledge_base/news/daily/news_brief_YYYYMMDD.md`.
- **Summarization**: A condensed version is created as `knowledge_base/news/daily/news_summary_YYYYMMDD.md` using the local `gemma3:12b` model.
- **Reindexing**: The script triggers a RAG reindex, making the new information available to Kaia immediately.

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
python tools/maintenance/update_kaia_news.py

# Generate with backfill (fills in missing days, uses more API quota)
python tools/maintenance/update_kaia_news.py --backfill

# Manual mode prompt generator (if no API key)
python tools/maintenance/update_kaia_news.py --manual
```

## 4. Manual Ingestion
If you manually generate a news brief (e.g., via the Gemini web interface), you can ingest it into Kaia's knowledge base using the ingestion tool:

1. Save your manual brief as a `.md`, `.txt`, or `.json` file in the root `news/` folder, `knowledge_base/news/daily/`, or `knowledge_base/news/weekly/`.
2. Name it with a date (e.g., `NEWS_BRIEF: 2026-02-01.md` or `WEEKLY_NEWS_BRIEF: 2026-01-26 to 2026-02-01.md`).
3. Run the ingestion script:
   ```bash
   python tools/maintenance/ingest_manual_news.py
   ```
The script will:
- Rename and move the file to the proper format (`news_brief_YYYYMMDD.md` for daily, `weekly_summary_YYYYMMDD.md` for weekly).
- Normalize headers (adding `## ` to category names) for RAG optimization and NewsManager compatibility.
- Generate a condensed summary (for daily briefs) using the local `gemma3:12b` model.
- Trigger a RAG reindex.

## 5. Automation
To enable fully automated daily updates:
1. **API Key**: Set the `GEMINI_API_KEY` in your `.env` file.
2. **Billing**: Enable billing on your Google Cloud project for higher API quota.
3. **Cron Job**: Add the script to your crontab.
   ```bash
   0 9 * * * cd /path/to/Kaiacord && source venv/bin/activate && python tools/maintenance/update_kaia_news.py
   ```

## 5. API Quota
- **Free tier**: 20 requests/day per model (may hit limits with backfill enabled)
- **Paid tier**: Enable billing at https://aistudio.google.com/ for higher limits
- **Tip**: Skip backfill (default) to conserve quota for today's news only

## 6. Maintenance
The script automatically archives news briefs and summaries older than **14 days** to `knowledge_base/news/archive/` to keep the knowledge base focused.

## 7. Formatting
Kaia's news responses are optimized for readability:
- **No Empty Lines**: Output is compact with no blank lines between sections.
- **Bullet Points**: News is presented as a numbered list with dates.
- **Options Footer**: Every news response includes a list of available categories for quick reference.

## 8. Dependencies
- **google-genai**: New Google GenAI SDK with grounding support
- **ollama**: For local summarization with gemma3:12b
