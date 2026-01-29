#!/usr/bin/env python3
"""
Daily News Updater for Kaia
Uses Gemini API to generate daily brief and adds to Kaia's knowledge base
"""

import os
import json
import datetime
try:
    import google.generativeai as genai
except ImportError:
    genai = None
from pathlib import Path
import ollama
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class KaiaNewsUpdater:
    def __init__(self, gemini_api_key: str):
        """Initialize with Gemini API key"""
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-flash-latest')
        self.knowledge_dir = Path("./knowledge_base/news/daily")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
    def generate_daily_brief(self, target_date: str = None) -> str:
        """Generate news brief using Gemini with RAG-optimized structure"""
        date_to_use = target_date or self.today
        
        prompt = f"""
Generate the news brief for Kaia for the date: {date_to_use}

Use this RAG-optimized structure:

# NEWS_BRIEF: {date_to_use}

## EXECUTIVE_SUMMARY
[3-4 sentences: High-level overview of the day's chaos, major geopolitical shifts, and tech landscape]

## TECH_OUTAGES_AND_FAILURES
- Azure/AWS/GCP: Downtime, latency, region failures
- ISP/CDN: Cloudflare, Akamai, major ISP outages
- Service X: Issue description, duration, impact

## SECURITY_INCIDENTS
- CVE-202X-XXXX: Critical vulnerabilities (CVSS > 7.0)
- Data Breaches: Company, records exposed, vector
- Ransomware: Active campaigns, major victims

## HACKER_CULTURE_AND_CYBERWARFARE
- Groups: Lapsus$, Anonymous, state-sponsored APT activity
- Leaks: Manifesto releases, source code dumps
- Events: Defcon/BlackHat news, major CTF results

## AI_DEVELOPMENTS
- Models: New LLM releases (OpenAI, Anthropic, Meta, Mistral)
- Open Source: HuggingFace trending, local LLM breakthroughs
- Regulation: EU AI Act updates, US executive orders

## US_POLITICS
- Legislation: Bills affecting privacy, crypto, surveillance, net neutrality
- Elections: Tech impact, disinformation campaigns, candidate stances on tech
- Agency Actions: FCC, FTC, NSA, CISA announcements

## GLOBAL_GEOPOLITICS
- Conflict: Cyber components of kinetic wars (Ukraine, Gaza, etc.)
- Trade: Chip bans, export controls, sanctions (US/China)
- Internet Freedom: Shutdowns, censorship, surveillance laws

## CULTURE_AND_ENTERTAINMENT
- Entertainment: Movie/TV releases, gaming news, celebrity tech impact
- Trends: Internet memes, viral challenges, digital subcultures
- Events: Concerts, art exhibitions, cultural festivals

## TECH_AND_SOCIETY
- Social Media: Platform changes (X/Twitter, Reddit, Bluesky), moderation scandals
- Crypto/Finance: Major hacks, regulatory crackdowns, ETF news
- Science: Space launches (SpaceX), breakthrough physics/bio

## FAILURE_METRICS
- Incidents today: X
- Downtime hours: Y
- Records exposed: Z

## QUOTES
- "[Direct quote about tech/politics]" - Name, Title
- "[Direct quote about security]" - Name, Title

## SOURCES
- Reuters
- BleepingComputer
- The Record
- 404 Media
- KrebsOnSecurity

---
**Generated**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}
**Format**: RAG-optimized technical digest

RULES:
1. Each bullet is one complete fact.
2. Include technical details: version numbers, CVEs, ASNs, bill numbers.
3. Keep language factual, no commentary.
4. **MINIMUM 40 bullet points total** across all sections.
5. **BROADEN SCOPE**: Don't just stick to enterprise tech. Include politics, war, and culture.
6. Prioritize events that affect systems, freedom, and infrastructure.
7. Use Kaia's vocabulary: "hiccups", "messed up", "glitch", "patch".
"""
        
        # Generate using Gemini
        response = self.model.generate_content(prompt)
        
        # Clean up response
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
        Extract the most critical 5-7 bullet points from this daily brief for immediate awareness.
        Format as very concise bullet points that can be quickly referenced.
        
        Brief:
        {full_brief[:2000]}
        
        Extract only facts that would be most relevant for a systems analyst monitoring critical infrastructure.
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

    def run(self):
        """Execute full update process"""
        # First, backfill missing news
        self.backfill_week()
        
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
        
        updater = KaiaNewsUpdater(api_key)
        updater.run()
