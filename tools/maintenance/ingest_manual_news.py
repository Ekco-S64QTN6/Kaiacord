#!/usr/bin/env python3
"""
Manual News Ingestion for Kaia
Converts manual news briefs into Kaia's standard format.
- Searches in ./news/, ./knowledge_base/news/daily/, and ./knowledge_base/news/weekly/
- Renames daily formats to 'news_brief_YYYYMMDD.md'
- Renames weekly formats to 'weekly_summary_YYYYMMDD.md'
- Normalizes headers to '## CATEGORY_NAME' for NewsManager compatibility
- Generates summaries using Ollama (qwen3.5:9b)
- Triggers RAG reindex
"""

import os
import re
import datetime
import json
from pathlib import Path
import ollama

KNOWLEDGE_DIR_DAILY = Path("./knowledge_base/news/daily")
KNOWLEDGE_DIR_WEEKLY = Path("./knowledge_base/news/weekly")

def ingest_manual_news():
    KNOWLEDGE_DIR_DAILY.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR_WEEKLY.mkdir(parents=True, exist_ok=True)
    
    # Potential source directories
    search_dirs = [KNOWLEDGE_DIR_DAILY, KNOWLEDGE_DIR_WEEKLY, Path("./news"), Path("./knowledge_base/news")]
    
    manual_files = []
    for sdir in search_dirs:
        if sdir.exists():
            # Match various patterns: "NEWS_BRIEF: 2026-02-01.md", "WEEKLY_NEWS_BRIEF: ...", etc.
            manual_files.extend(list(sdir.glob("*NEWS_BRIEF: *.md")))
            manual_files.extend(list(sdir.glob("news_brief_*.md")))
            manual_files.extend(list(sdir.glob("weekly_summary_*.md")))
            manual_files.extend(list(sdir.glob("news_*.json")))
            manual_files.extend(list(sdir.glob("manual_news_*.md")))
            manual_files.extend(list(sdir.glob("*.txt")))
    
    ingested_count = 0

    # 1. Process and Move manual files
    for file in manual_files:
        is_weekly = "WEEKLY" in file.name.upper()
        
        # Try to extract date
        # Matches YYYY-MM-DD, YYYY.MM.DD, YYYY_MM_DD, and YYYYMMDD
        date_match = re.search(r'(\d{4})[-_\.]?(\d{2})[-_\.]?(\d{2})', file.name)
        if not date_match:
            print(f"⚠️ Could not extract date from filename: {file.name}")
            continue
            
        year, month, day = date_match.groups()
        clean_date = f"{year}{month}{day}"
        target_date = f"{year}-{month}-{day}"
        
        if is_weekly:
            dest_filename = f"weekly_summary_{clean_date}.md"
            dest_path = KNOWLEDGE_DIR_WEEKLY / dest_filename
        else:
            dest_filename = f"news_brief_{clean_date}.md"
            dest_path = KNOWLEDGE_DIR_DAILY / dest_filename
        
        
        # Handle JSON conversion if needed
        content = ""
        if file.suffix.lower() == ".json":
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    header_text = "WEEKLY NEWS SUMMARY" if is_weekly else "NEWS_BRIEF"
                    content = f"# {header_text}: {target_date}\n\n"
                    for key, val in data.items():
                        content += f"## {key.upper()}\n{val}\n\n"
                else:
                    content = str(data)
            except Exception as e:
                print(f"❌ Failed to parse JSON {file.name}: {e}")
                continue
        else:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                print(f"❌ Failed to read {file.name}: {e}")
                continue
                
        # --- NORMALIZE HEADERS ---
        lines = content.split('\n')
        normalized_lines = []
        
        # 1. Primary Title
        title_pattern = "# NEWS_BRIEF:" if not is_weekly else "# WEEKLY NEWS SUMMARY:"
        if not content.strip().startswith(title_pattern):
            normalized_lines.append(f"{title_pattern} {target_date}")
            normalized_lines.append("")
            # If original started with the title without #, skip first line
            if content.strip().startswith("WEEKLY_NEWS_BRIEF:") or content.strip().startswith("NEWS_BRIEF:"):
                lines = lines[1:]

        # 2. Sub-headers (Normalize to ## CATEGORY for NewsManager)
        # Matches uppercase words like TECH_OUTAGES_AND_FAILURES or SECURITY_INCIDENTS
        header_re = re.compile(r'^([A-Z][A-Z0-9_ ]{3,30})$')
        
        for line in lines:
            stripped = line.strip()
            if header_re.match(stripped) and not stripped.startswith('#'):
                normalized_lines.append(f"## {stripped}")
            else:
                normalized_lines.append(line.rstrip())
        
        content = '\n'.join(normalized_lines)
        
        # Write back to the proper location ONLY if content changed
        has_changed = True
        if dest_path.exists():
            try:
                with open(dest_path, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                if old_content.strip() == content.strip():
                    has_changed = False
            except Exception:
                pass
        
        if has_changed:
            ingested_count += 1
            print(f"\n📄 Ingesting: {file.name}")
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Delete original if different
            if file.absolute() != dest_path.absolute():
                file.unlink()
                print(f"✓ Moved and normalized as: {dest_filename}")
            else:
                print(f"✓ Normalized in-place: {dest_filename}")
        else:
            # If it's the exact same content, we still delete the temporary 'news_*.json' 
            # or extra files that match the glob to keep it clean.
            if file.absolute() != dest_path.absolute():
                file.unlink()
                print(f"✓ Content identical, cleaned up source: {file.name}")

    # 2. Check for missing summaries (ONLY for Daily for now, as Weekly IS a summary)
    summarized_count = 0
    all_briefs = list(KNOWLEDGE_DIR_DAILY.glob("news_brief_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].md"))
    for brief_path in all_briefs:
        clean_date = brief_path.stem.split('_')[-1]
        target_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"
        summary_filename = f"news_summary_{clean_date}.md"
        summary_path = KNOWLEDGE_DIR_DAILY / summary_filename
        
        if summary_path.exists():
            continue
            
        # Only summarize if the news is from the last 7 days to avoid GPU churn on old restored files
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=7)
        try:
            current_date = datetime.datetime.strptime(clean_date, "%Y%m%d")
            if current_date < cutoff_date:
                # Still count as "manual" but skip intense GPU work
                print(f"⏭️ Skipping summary for old brief: {brief_path.name} (Cutoff: {cutoff_date.strftime('%Y%m%d')})")
                continue
        except Exception:
            pass

        summarized_count += 1
        print(f"🧠 Generating summary for: {brief_path.name}")
        try:
            with open(brief_path, 'r', encoding='utf-8') as f:
                full_brief = f.read()
            generate_summary(full_brief, target_date, summary_path)
        except Exception as e:
            print(f"❌ Failed to process {brief_path.name}: {e}")
            
    # Trigger reindex if work was done
    if ingested_count > 0 or summarized_count > 0:
        trigger_file = KNOWLEDGE_DIR_DAILY.parent / ".trigger_reindex"
        trigger_file.touch()
        print(f"\n✅ Ingested {ingested_count} files and generated {summarized_count} summaries. RAG reindex triggered.")

def generate_summary(full_brief, target_date, summary_path):
    summary_prompt = f"""
    Create a BALANCED news summary with 1-2 bullet points from EACH category below.
    Format as concise bullet points grouped by category.
    
    SOURCE BRIEF:
    {full_brief[:4000]}
    
    REQUIRED CATEGORIES (include 1-2 items from EACH):
    - **General/World**: Major breaking world news
    - **Politics**: US or international political developments
    - **Business/Economy**: Markets, companies, economic news
    - **Culture/Entertainment**: Movies, sports, celebrity, trends
    - **Science/Health**: Medical, space, research, environment
    - **Technology**: AI, consumer tech, industry news
    - **Security**: Only if major (breaches, CVEs for !news hacker)
    
    CRITICAL RULES:
    1. Keep each bullet to ONE sentence. Total: 10-14 bullets covering ALL categories.
    2. DO NOT invent or hallucinate specific numbers or statistics.
    3. NO blank lines between bullets or categories.
    4. Start each category header on its own line immediately followed by its bullets.
    """
    
    try:
        response = ollama.chat(
            model='qwen3.5:9b',
            messages=[
                {'role': 'system', 'content': 'You extract concise technical bullet points from news briefs.'},
                {'role': 'user', 'content': summary_prompt}
            ]
        )
        
        summary = response['message']['content']
        final_summary = f"# QUICK REFERENCE: {target_date}\n\n{summary}"
        
        # Check if changed
        if summary_path.exists():
            with open(summary_path, 'r', encoding='utf-8') as f:
                if f.read().strip() == final_summary.strip():
                    return

        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(final_summary)
        print(f"✓ Created summary: {summary_path.name}")
        
    except Exception as e:
        print(f"⚠️ Could not create summary: {e}")
        lines = full_brief.split('\n')
        bullet_lines = [line for line in lines if line.strip().startswith('- ')]
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"# QUICK REFERENCE: {target_date}\n\n" + '\n'.join(bullet_lines[:10]))
        print(f"✓ Created fallback summary from bullets.")

if __name__ == "__main__":
    ingest_manual_news()
