#!/usr/bin/env python3
"""
Daily News Updater for Kaia
Uses Gemini API with Google Search grounding to generate accurate daily briefs
"""

import os
import json
import datetime
from pathlib import Path
import ollama
from dotenv import load_dotenv

# New Google GenAI SDK
from google import genai
from google.genai import types

# Load environment variables from .env file
load_dotenv()

class KaiaNewsUpdater:
    def __init__(self, gemini_api_key: str):
        """Initialize with Gemini API key"""
        self.client = genai.Client(api_key=gemini_api_key)
        self.model_name = 'gemini-2.0-flash'  # Using a stable model with grounding support
        self.knowledge_dir = Path("./knowledge_base/news/daily")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
    def generate_daily_brief(self, target_date: str = None) -> str:
        """Generate news brief using Gemini with Google Search grounding for accuracy"""
        date_to_use = target_date or self.today
        
        prompt = f"""You are a news aggregator. Search for and compile REAL news stories from today ({date_to_use}).

CRITICAL: You MUST use Google Search to find actual news. Do NOT invent or hallucinate any stories.
Only include news items that you can verify from your search results.

Compile the news into this structure:

# NEWS_BRIEF: {date_to_use}

## EXECUTIVE_SUMMARY
[3-4 sentences summarizing the major verified news of the day]

## GENERAL_NEWS
- World Events: Major breaking news stories (with source)
- International: Significant global developments
- Domestic: Important national news, policy changes

## US_POLITICS
- White House: Presidential actions, announcements
- Congress: Major legislation, votes
- Elections: Campaign news, polls

## GLOBAL_GEOPOLITICS
- International Relations: Diplomacy, treaties
- Conflicts: Ongoing situations, peace negotiations
- Trade: Trade deals, tariffs, sanctions

## CULTURE_AND_ENTERTAINMENT
- Entertainment: Movie/TV releases, awards
- Sports: Major games, championships
- Trends: Viral stories, pop culture

## SCIENCE_AND_HEALTH
- Medical: Health news, breakthroughs
- Space: NASA, SpaceX, astronomy
- Environment: Climate news, natural disasters

## BUSINESS_AND_ECONOMY
- Markets: Stock market, crypto movements
- Companies: Major corporate news
- Jobs: Employment trends

## TECHNOLOGY
- AI: New developments, regulations
- Consumer Tech: Product launches
- Industry: Tech company news

## SECURITY_INCIDENTS
- Vulnerabilities: Critical CVEs (if any)
- Data Breaches: Major incidents
- Ransomware: Active campaigns

## SOURCES
[List the news sources you found these stories from]

---
**Generated**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}

RULES:
1. ONLY include news you found via search - NO invented stories.
2. Each bullet should be one complete, verified fact.
3. Include source names when possible (e.g., "per Reuters", "according to AP").
4. If you cannot find news for a category, write "No major news in this category today."
5. Prioritize major, widely-reported stories over obscure ones.
"""
        
        # Generate using Gemini WITH Google Search grounding (new SDK syntax)
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(google_search=types.GoogleSearch())
                    ]
                ),
            )
            brief = response.text.strip()
            
            # Log grounding metadata if available
            try:
                metadata = response.candidates[0].grounding_metadata
                if metadata and metadata.web_search_queries:
                    print(f"✓ Grounding used search queries: {metadata.web_search_queries}")
            except:
                pass
                
        except Exception as e:
            print(f"⚠️ Grounding failed ({e}), falling back to standard generation")
            # Fallback to standard generation if grounding fails
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            brief = response.text.strip()
        
        return brief
    
    def save_to_knowledge_base(self, brief: str, target_date: str = None):
        """Save the brief to Kaia's knowledge base"""
        date_to_use = target_date or self.today
        # Create daily file
        filename = f"news_brief_{date_to_use.replace('-', '')}.md"
        filepath = self.knowledge_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        print(f"✓ Saved daily brief to: {filepath}")
        
        # Also create a summary for immediate ingestion
        self.create_summary_for_rag(brief, date_to_use)
    
    def create_summary_for_rag(self, full_brief: str, target_date: str = None):
        """Create a condensed version optimized for RAG retrieval"""
        date_to_use = target_date or self.today
        
        # Use Ollama to create a summary
        summary_prompt = f"""
        Create a BALANCED news summary with 1-2 bullet points from EACH category below.
        Format as concise bullet points grouped by category.
        
        SOURCE BRIEF:
        {full_brief[:3000]}
        
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
        2. DO NOT invent or hallucinate specific numbers, prices, statistics, or data points that are NOT in the source brief.
        3. If the source doesn't include a specific number (like stock prices, gold prices, dollar amounts), describe the trend WITHOUT the specific number.
        4. NO blank lines between bullets or categories - output should be compact with no empty lines.
        5. Start each category header on its own line immediately followed by its bullets.
        """
        
        try:
            response = ollama.chat(
                model='gemma3:12b',
                messages=[
                    {'role': 'system', 'content': 'You extract concise technical bullet points from news briefs.'},
                    {'role': 'user', 'content': summary_prompt}
                ]
            )
            
            summary = response['message']['content']
            
            # Save summary
            summary_file = self.knowledge_dir / f"news_summary_{date_to_use.replace('-', '')}.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# QUICK REFERENCE: {date_to_use}\n\n{summary}")
            
            print(f"✓ Created quick reference: {summary_file}")
            
        except Exception as e:
            print(f"⚠️ Could not create summary: {e}")
            # Save raw brief as summary
            summary_file = self.knowledge_dir / f"news_summary_{date_to_use.replace('-', '')}.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                # Extract just bullet points
                lines = full_brief.split('\n')
                bullet_lines = [line for line in lines if line.strip().startswith('- ')]
                f.write(f"# QUICK REFERENCE: {date_to_use}\n\n" + '\n'.join(bullet_lines[:10]))
    
    def clean_old_briefs(self, keep_days: int = 14):
        """Archive news briefs older than specified days instead of deleting"""
        news_files = list(self.knowledge_dir.glob("news_*.md"))
        
        # Create archive directory
        archive_dir = self.knowledge_dir.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=keep_days)
        
        archived = 0
        for file in news_files:
            # Try to extract date from filename
            try:
                if 'brief' in file.name or 'summary' in file.name:
                    # File format: news_brief_20260121.md or news_summary_20260121.md
                    date_str = file.stem.split('_')[-1]
                    file_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    
                    if file_date < cutoff_date:
                        # Move to archive instead of delete
                        archive_path = archive_dir / file.name
                        file.rename(archive_path)
                        archived += 1
            except:
                continue
        
        if archived > 0:
            print(f"✓ Archived {archived} old news files to {archive_dir}")

    
    def backfill_week(self):
        """Check for and generate news for the last 7 days if missing"""
        print("🔍 Checking for missing news briefs in the last 7 days...")
        
        for i in range(7, 0, -1):
            date_obj = datetime.datetime.now() - datetime.timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")
            filename = f"news_brief_{date_str.replace('-', '')}.md"
            filepath = self.knowledge_dir / filename
            
            if not filepath.exists():
                print(f"📅 Backfilling news for {date_str}...")
                try:
                    brief = self.generate_daily_brief(date_str)
                    self.save_to_knowledge_base(brief, date_str)
                except Exception as e:
                    print(f"❌ Failed to backfill {date_str}: {e}")
            else:
                print(f"✅ News for {date_str} already exists.")

    def run(self, skip_backfill: bool = True):
        """Execute full update process"""
        # Backfill disabled by default to conserve API quota
        # Enable with --backfill flag
        if not skip_backfill:
            self.backfill_week()
        else:
            print("ℹ️ Skipping backfill to conserve API quota. Use --backfill to enable.")
        
        # Check if today's news already exists (prevent duplicate regeneration)
        today_filename = f"news_brief_{self.today.replace('-', '')}.md"
        today_filepath = self.knowledge_dir / today_filename
        
        if today_filepath.exists():
            print(f"\n✅ Today's news ({self.today}) already exists at {today_filepath}")
            print("   Skipping generation. Delete the file to force regeneration.")
            # Still clean old files to maintain retention
            self.clean_old_briefs()
            return
        
        print(f"\n📰 Generating daily news brief for {self.today}...")
        
        try:
            # Generate brief
            brief = self.generate_daily_brief()
            print("✓ Brief generated successfully")
            
            # Save to knowledge base
            self.save_to_knowledge_base(brief)
            
            # Verify file was actually saved
            if today_filepath.exists():
                print(f"✓ Verified: {today_filepath} exists ({today_filepath.stat().st_size} bytes)")
            else:
                print(f"⚠️ WARNING: File {today_filepath} was not saved!")
            
            # Clean old files
            self.clean_old_briefs()
            
            # Optional: Trigger RAG reindex
            self.trigger_reindex()
            
            print(f"\n✅ Daily update complete for {self.today}")
            print(f"   Kaia now has current news up to {self.today}")
            
        except Exception as e:
            print(f"❌ Error generating daily brief: {e}")
    
    def trigger_reindex(self):
        """Optionally trigger RAG reindexing"""
        # This would depend on how your Kaiacord handles new files
        # One approach: create a trigger file
        trigger_file = self.knowledge_dir.parent / ".trigger_reindex"
        trigger_file.touch()
        print("✓ Reindex trigger created")
        
        # Also create a small python script to trigger it if needed
        # Path is relative to knowledge_base/news/daily
        trigger_script = self.knowledge_dir.parent.parent.parent / "tools" / "trigger_reindex.py"
        if not trigger_script.exists():
            with open(trigger_script, 'w') as f:
                f.write("import os\nfrom pathlib import Path\nPath('./knowledge_base/.trigger_reindex').touch()\nprint('RAG reindex triggered.')\n")

# Manual version for when you don't have Gemini API
def manual_news_update():
    """Manual method: copy/paste the prompt into Gemini web interface"""
    
    prompt = f"""
    Go to https://gemini.google.com/
    
    Paste this exact prompt:
    
    ```
    Generate today's ({datetime.datetime.now().strftime("%Y-%m-%d")}) daily news digest for Kaia using the format and rules specified.
    
    Kaia is a systems analyst/hacker persona who needs factual, technical updates without commentary.
    
    Focus on:
    - Infrastructure outages and tech failures
    - Cybersecurity incidents and vulnerabilities
    - Internet governance and network events
    - AI/ML developments with practical implications
    - **US Politics**: Legislation, elections, policy changes affecting tech/society
    - **Global Geopolitics**: Conflicts, treaties, international relations
    - **Hacker Culture**: Leaks, Defcon, community events
    - **General Tech**: Social media, crypto, science
    
    Use technical details where relevant (version numbers, CVEs, protocols).
    Present facts without opinion or sensationalism.
    Include concrete data points and statistics.
    
    **CRITICAL**: Generate at least 40 bullet points total. Cover all sections.
    
    Now generate the daily brief for {datetime.datetime.now().strftime("%Y-%m-%d")}.
    ```
    
    Copy the output and save it as: ./knowledge_base/news_brief_{datetime.datetime.now().strftime("%Y%m%d")}.md
    """
    
    print(prompt)
    
    # Create a simple script to help
    script = f"""#!/bin/bash
# Save this as update_kaia.sh
echo "1. Go to: https://gemini.google.com/"
echo "2. Copy the prompt from: daily_prompt.txt"
echo "3. Paste into Gemini and copy the output"
echo "4. Save output to: knowledge_base/news_brief_{datetime.datetime.now().strftime("%Y%m%d")}.md"
echo "5. Restart Kaia or wait for auto-reindex"
"""
    
    with open("update_kaia_manual.sh", "w") as f:
        f.write(script)
    
    print(f"\n📋 Manual update script created: update_kaia_manual.sh")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        manual_news_update()
    else:
        # Check for Gemini API key
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            print("❌ GEMINI_API_KEY environment variable not set")
            print("\nEither:")
            print("1. Set GEMINI_API_KEY and run: python update_kaia_news.py")
            print("2. Run manual version: python update_kaia_news.py --manual")
            sys.exit(1)
        
        # Check for --backfill flag
        do_backfill = "--backfill" in sys.argv
        
        updater = KaiaNewsUpdater(api_key)
        updater.run(skip_backfill=not do_backfill)
