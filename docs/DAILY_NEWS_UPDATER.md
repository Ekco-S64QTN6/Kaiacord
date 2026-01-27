# Daily News Updater
The Daily News Updater is an automated system that keeps Kaia informed about current events, specifically focusing on tech, cybersecurity, infrastructure, and culture.

## 1. How it Works
The system uses the Gemini API to generate a daily technical brief based on current events. This brief is then processed by Kaia's local LLM to create a quick-reference summary optimized for RAG retrieval.

- **Generation**: `tools/update_kaia_news.py` calls the Gemini API (`gemini-flash-latest`) with a specific persona-aligned prompt.
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

## 3. Automation
To enable fully automated daily updates:
1. **API Key**: Set the `GEMINI_API_KEY` in your `.env` file.
2. **Cron Job**: Add the script to your crontab.
   ```bash
   0 9 * * * cd /path/to/Kaiacord && python tools/update_kaia_news.py
   ```

## 4. Manual Fallback
If an API key is not available, you can use the manual method:
1. Run `python tools/update_kaia_news.py --manual`.
2. Copy the generated prompt into the [Gemini Web Interface](https://gemini.google.com/).
3. Save the output as `knowledge_base/news/daily/news_brief_YYYYMMDD.md`.
4. Kaia will automatically index the new file.

## 5. Maintenance
The script automatically removes news briefs and summaries older than **14 days** to keep the knowledge base focused and prevent context bloat.

## 6. Formatting
Kaia's news responses are optimized for readability:
- **No Commentary**: Opening and closing lines are removed to focus on the facts.
- **Bullet Points**: News is presented as a numbered list with dates.
- **Options Footer**: Every news response includes a list of available categories for quick reference.
