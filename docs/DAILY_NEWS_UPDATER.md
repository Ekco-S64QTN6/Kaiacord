# Daily News Updater
The Daily News Updater is an automated system that keeps Kaia informed about current events, specifically focusing on tech, cybersecurity, and infrastructure.

## 1. How it Works
The system uses the Gemini API to generate a daily technical brief based on current events. This brief is then processed by Kaia's local LLM to create a quick-reference summary optimized for RAG retrieval.

- **Generation**: `update_kaia_news.py` calls the Gemini API (`gemini-flash-latest`) with a specific persona-aligned prompt.
- **Ingestion**: The brief is saved to `knowledge_base/news_brief_YYYYMMDD.md`.
- **Summarization**: A condensed version is created as `knowledge_base/news_summary_YYYYMMDD.md` using the local `gemma3:12b` model.
- **Reindexing**: The script triggers a RAG reindex, making the new information available to Kaia immediately.

## 2. Automation
To enable fully automated daily updates:
1. **API Key**: Set the `GEMINI_API_KEY` in your `.env` file.
2. **Cron Job**: Add the script to your crontab.
   ```bash
   0 9 * * * cd /path/to/Kaiacord && python update_kaia_news.py
   ```

## 3. Manual Fallback
If an API key is not available, you can use the manual method:
1. Run `python update_kaia_news.py --manual`.
2. Copy the generated prompt into the [Gemini Web Interface](https://gemini.google.com/).
3. Save the output as `knowledge_base/news_brief_YYYYMMDD.md`.
4. Kaia will automatically index the new file.

## 4. Maintenance
The script automatically removes news briefs and summaries older than **7 days** to keep the knowledge base focused and prevent context bloat.
