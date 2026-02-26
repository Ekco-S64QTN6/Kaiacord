#!/usr/bin/env python3
import warnings
# Silence "nag" about switching to google-genai
warnings.filterwarnings("ignore", category=FutureWarning)
import os
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import ollama
from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

class KaiaNewsUpdater:
    def __init__(self, gemini_api_key: str):
        """Initialize with Gemini API key"""
        genai.configure(api_key=gemini_api_key)
        # USE 'gemini-flash-latest' FOR FREE ACCOUNTS.
        # This is the correct alias for Gemini 1.5 Flash in the legacy SDK.
        self.model_name = 'gemini-flash-latest' 
        self.knowledge_dir = Path("./knowledge_base/news/daily")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
    def generate_daily_brief(self, target_date: str = None) -> str:
        """Generate news brief using Gemini with Google Search grounding for accuracy"""
        date_to_use = target_date or self.today
        
        prompt = f"""You are a news aggregator. Search for and compile REAL news stories from today ({date_to_use}).

CRITICAL: You MUST use Google Search to find actual news. Do NOT invent or hallucinate any stories.
Only include news items that you can verify from your search results.

TARGET SOURCES FOR TECHNOLOGY & SECURITY:
- Ars Technica (arstechnica.com)
- BleepingComputer (bleepingcomputer.com)
- The Verge (theverge.com)
- Wired (wired.com)
- Hacker News (news.ycombinator.com)
- Slashdot (slashdot.org)
- TechCrunch (techcrunch.com)

Compile the news into this structure:

# NEWS_BRIEF: {date_to_use}

## EXECUTIVE_SUMMARY
[3-4 sentences: A professional overview of today's top stories, including major geopolitical developments and important technical trends.]

## GENERAL_NEWS
- World Events: Major breaking news items - *Source*
- International: Significant global developments - *Source*
- Domestic: Important national news, policy changes - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of general news] - Name, Title

## US_POLITICS
- White House: Presidential actions, announcements - *Source*
- Congress: Major legislation, votes - *Source*
- Elections: Campaign news, polls - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of US politics] - Name, Title

## GLOBAL_GEOPOLITICS
- International Relations: Diplomacy, treaties - *Source*
- Conflicts: Ongoing situations, peace negotiations - *Source*
- Trade: Trade deals, tariffs, sanctions - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of global affairs] - Name, Title

## CULTURE_AND_ENTERTAINMENT
- Entertainment: Movie/TV releases, awards - *Source*
- Sports: Major games, championships - *Source*
- Trends: Viral stories, pop culture - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of culture/entertainment] - Name, Title

## SCIENCE_AND_HEALTH
- Medical: Health news, breakthroughs - *Source*
- Space: NASA, SpaceX, astronomy - *Source*
- Environment: Climate news, natural disasters - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of science/health] - Name, Title

## BUSINESS_AND_ECONOMY
- Markets: Stock market, crypto movements - *Source*
- Companies: Major corporate news - *Source*
- Jobs: Employment trends - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of business/economy] - Name, Title

## TECHNOLOGY_AND_INFRASTRUCTURE
- AI: New developments, regulations, LLM releases - *Source*
- Infrastructure: Major cloud outages (AWS/Azure/GCP), ISP failures - *Source*
- Hardware: Chip manufacturing, consumer electronics launches - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of tech/AI] - Name, Title

## SECURITY_INCIDENTS
- Vulnerabilities: Critical CVEs, zero-day exploits - *Source*
- Data Breaches: Major corporate leaks, exposed databases - *Source*
- Ransomware: Active extortion campaigns, new threat actors - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of security] - Name, Title

## HACKER_CULTURE
- Hacktivism: Group manifestos, major breaches for social causes - *Source*
- Community: DEFCON/BlackHat updates, new hacking tools - *Source*
- Cyberwarfare: State-sponsored operations, offensive signal metrics - *Source*
- QUOTE: [Include a notable quote specifically from today's coverage of hacker culture] - Name, Title

---
**Generated**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}

RULES:
1. ONLY include news you found via search - NO invented stories.
2. Each bullet should be one complete, verified fact.
3. **SOURCE ATTRIBUTION**: Every single news bullet MUST end with `- *Source Name*` representing where the info was found.
4. **CATEGORY QUOTES**: Every section (except EXECUTIVE_SUMMARY) must include a "QUOTE:" bullet at the end. The quote MUST be taken from today's news coverage/sources specifically about that topic.
5. BROADEN SCOPE: Ensure ALL categories above are populated.
6. Do NOT include a 'SOURCES' or 'REFERENCES' section at the end of the brief.
"""
        
        # In legacy google-generativeai, grounding is enabled via tools
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                tools='google_search_retrieval'
            )
            
            response = model.generate_content(prompt)
            
            # Robust text extraction
            brief = (response.text or "").strip()
            
            if not brief:
                # Check for candidates and finish reason
                if response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                    raise ValueError(f"Empty response text (Finish Reason: {finish_reason})")
                else:
                    raise ValueError("Empty response feedback (no candidates)")
                
        except Exception as e:
            error_msg = f"Grounding failed ({e}). Refusing to fall back to ungrounded standard generation to prevent hallucinated news."
            print(f"❌ CRITICAL: {error_msg}")
            raise Exception(error_msg)
        
        return brief
    
    def save_to_knowledge_base(self, brief: str, target_date: str = None):
        """Save the brief to Kaia's knowledge base"""
        date_to_use = target_date or self.today
        # Create daily file
        filename = f"news_brief_{date_to_use.replace('-', '')}.md"
        filepath = self.knowledge_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        print(f"[DEBUG] Saved daily brief to: {filepath}")
        
        # Also create a summary for immediate ingestion
        self.create_summary_for_rag(brief, date_to_use)
    
    def create_summary_for_rag(self, full_brief: str, target_date: str = None):
        """Create a condensed version optimized for RAG retrieval"""
        date_to_use = target_date or self.today
        
        # Use Ollama to create a summary
        summary_prompt = f"""
        Create a high-density, ultra-concise news summary.
        Format as short bullet points grouped by category.
        
        SOURCE BRIEF:
        {full_brief[:3500]}
        
        CATEGORIES:
        - ## Technology: AI, LLM releases, hardware, cloud, infrastructure
        - ## Security: CVEs, zero-days, breaches, ransomware
        - ## Hacker Culture: Leaks, hacktivism, community news
        - ## Geopolitics: International relations, world events, policy
        - ## Science & Health: Space, research, breakthroughs
        
        CRITICAL RULES:
        1. MAXIMUM 10-12 bullets TOTAL for the entire document.
        2. NO "No news provided" items. If a category has no info, SKIP it entirely.
        3. Keep each bullet to ONE SHORT sentence.
        4. TOTAL character count must be under 1400 characters.
        5. Use "## CategoryName" for headers.
        6. NO blank lines between bullets.
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
                f.write(summary)
            
            print(f"[DEBUG] Created quick reference: {summary_file}")
            
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
            except Exception:
                continue
        
        if archived > 0:
            print(f"[DEBUG] Archived {archived} old news files to {archive_dir}")

    def get_latest_existing_brief(self) -> tuple[Optional[str], Optional[str]]:
        """Find the most recent news brief in daily or archive folders"""
        # Check daily dir first
        briefs = list(self.knowledge_dir.glob("news_brief_*.md"))
        
        # Then check archive
        archive_dir = self.knowledge_dir.parent / "archive"
        if archive_dir.exists():
            briefs.extend(list(archive_dir.glob("news_brief_*.md")))
            
        if not briefs:
            return None, None
            
        # Sort by filename (contains date)
        briefs.sort(key=lambda x: x.name, reverse=True)
        latest_file = briefs[0]
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # Extract date from filename news_brief_YYYYMMDD.md
            date_str = latest_file.stem.split('_')[-1]
            return content, date_str
        except Exception as e:
            print(f"⚠️ Failed to read latest brief {latest_file}: {e}")
            return None, None


    
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
                print(f"[DEBUG] News for {date_str} already exists.")

    def run(self, skip_backfill: bool = True):
        """Execute full update process"""
        # Backfill disabled by default to conserve API quota
        # Enable with --backfill flag
        if not skip_backfill:
            self.backfill_week()
        else:
            print("[DEBUG] Skipping backfill to conserve API quota. Use --backfill to enable.")
        
        # Check if today's news already exists (prevent duplicate regeneration)
        today_filename = f"news_brief_{self.today.replace('-', '')}.md"
        today_filepath = self.knowledge_dir / today_filename
        
        if today_filepath.exists():
            print(f"[DEBUG] Today's news ({self.today}) already exists. Skipping generation.")
            # Still clean old files to maintain retention
            self.clean_old_briefs()
            return
        
        print(f"\n📰 Generating daily news brief for {self.today}...")
        
        try:
            # Generate brief
            brief = self.generate_daily_brief()
            print("[DEBUG] Brief generated successfully")
            
            # Save to knowledge base
            self.save_to_knowledge_base(brief)
            
            # Verify file was actually saved
            if today_filepath.exists():
                print(f"[DEBUG] Verified: {today_filepath} exists")
            else:
                print(f"⚠️ WARNING: File {today_filepath} was not saved!")
            
            # Clean old files
            self.clean_old_briefs()
            
            # Optional: Trigger RAG reindex
            self.trigger_reindex()
            
            print(f"\n✅ Daily update complete for {self.today}")
            
        except Exception as e:
            error_str = str(e)
            print(f"❌ Error generating daily brief: {error_str}")
            
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print("⚠️ Gemini API quota exhausted. Skipping update.")
            else:
                print("\n❌ Unknown error. Skipping update.")
            
            # Re-raise to ensure failures are propagated to the background task manager
            raise e
    
    def trigger_reindex(self):
        """Optionally trigger RAG reindexing"""
        # This would depend on how your Kaiacord handles new files
        # One approach: create a trigger file
        trigger_file = self.knowledge_dir.parent / ".trigger_reindex"
        trigger_file.touch()
        print("[DEBUG] Reindex trigger created")
        
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
    Do NOT include a "SOURCES" or "REFERENCES" section at the end.
    
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
