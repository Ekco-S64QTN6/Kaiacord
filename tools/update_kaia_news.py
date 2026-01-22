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
        self.knowledge_dir = Path("./knowledge_base")
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
    def generate_daily_brief(self) -> str:
        """Generate daily news brief using Gemini with RAG-optimized structure"""
        
        prompt = f"""
Generate today's news brief for Kaia using this RAG-optimized structure:

# NEWS_BRIEF: {self.today}

## EXECUTIVE_SUMMARY
[2-3 sentences: Overall technical landscape]

## TECH_OUTAGES
- Azure: Intermittent slowdowns in multiple regions, network congestion
- Service X: Issue description, duration, impact

## SECURITY_INCIDENTS
- CVE-202X-XXXX: Buffer overflow in [software], CVSS X.X
- Breach: Company name, records exposed, cause

## HARDWARE_RELEASES  
- NVIDIA: Product name, specs, availability
- AMD: Product name, specs
- Samsung: Product name, context about past issues

## INTERNET_INFRASTRUCTURE
- BGP incident: Brief description, duration, AS numbers
- DNS changes: TLD updates, root server maintenance
- CDN performance: Stats, changes

## AI_DEVELOPMENTS
- Model releases: Name, parameters, license
- Regulations: Country, law name, impact
- Research: Key paper findings

## GEOPOLITICAL_TECH
- Legislation: Country, bill name, tech impact
- Trade: Restrictions on chips/software
- Surveillance: New powers, technology used

## FAILURE_METRICS
- Incidents today: X
- Downtime hours: Y
- Records exposed: Z

## QUOTES
- "[Direct quote about tech issue]" - Name, Title
- "[Direct quote about security]" - Name, Title

## TIMELINE
- 09:00 UTC: Azure latency spikes begin
- 11:30 UTC: CVE disclosure published
- 15:00 UTC: SpaceX launch window opens

## SOURCES
- Reuters
- BleepingComputer  
- AWS Status Page
- CVE database

---
**Generated**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}
**Format**: RAG-optimized technical digest

RULES:
1. Each bullet is one complete fact
2. Include technical details: version numbers, CVEs, ASNs, etc.
3. Keep language factual, no commentary
4. Maximum 15 bullet points total across all sections
5. Prioritize events that affect systems Kaia would care about
6. Include historical context when relevant (e.g., "after S21 fiasco")
7. Use Kaia's vocabulary: "hiccups" not "issues", "messed up" not "configuration error"
"""
        
        # Generate using Gemini
        response = self.model.generate_content(prompt)
        
        # Clean up response
        brief = response.text.strip()
        
        return brief
    
    def save_to_knowledge_base(self, brief: str):
        """Save the brief to Kaia's knowledge base"""
        # Create daily file
        filename = f"news_brief_{self.today.replace('-', '')}.md"
        filepath = self.knowledge_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        print(f"✓ Saved daily brief to: {filepath}")
        
        # Also create a summary for immediate ingestion
        self.create_summary_for_rag(brief)
    
    def create_summary_for_rag(self, full_brief: str):
        """Create a condensed version optimized for RAG retrieval"""
        
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
            summary_file = self.knowledge_dir / f"news_summary_{self.today.replace('-', '')}.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# QUICK REFERENCE: {self.today}\n\n{summary}")
            
            print(f"✓ Created quick reference: {summary_file}")
            
        except Exception as e:
            print(f"⚠️ Could not create summary: {e}")
            # Save raw brief as summary
            summary_file = self.knowledge_dir / f"news_summary_{self.today.replace('-', '')}.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                # Extract just bullet points
                lines = full_brief.split('\n')
                bullet_lines = [line for line in lines if line.strip().startswith('- ')]
                f.write(f"# QUICK REFERENCE: {self.today}\n\n" + '\n'.join(bullet_lines[:10]))
    
    def clean_old_briefs(self, keep_days: int = 7):
        """Remove news briefs older than specified days"""
        news_files = list(self.knowledge_dir.glob("news_*.md"))
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=keep_days)
        
        removed = 0
        for file in news_files:
            # Try to extract date from filename
            try:
                if 'brief' in file.name or 'summary' in file.name:
                    # File format: news_brief_20260121.md or news_summary_20260121.md
                    date_str = file.stem.split('_')[-1]
                    file_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    
                    if file_date < cutoff_date:
                        file.unlink()
                        removed += 1
            except:
                continue
        
        if removed > 0:
            print(f"✓ Removed {removed} old news files")
    
    def run(self):
        """Execute full update process"""
        print(f"📰 Generating daily news brief for {self.today}...")
        
        try:
            # Generate brief
            brief = self.generate_daily_brief()
            print("✓ Brief generated successfully")
            
            # Save to knowledge base
            self.save_to_knowledge_base(brief)
            
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
        trigger_file = self.knowledge_dir / ".trigger_reindex"
        trigger_file.touch()
        print("✓ Reindex trigger created")
        
        # Also create a small python script to trigger it if needed
        trigger_script = self.knowledge_dir.parent / "tools" / "trigger_reindex.py"
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
    - Geopolitical events affecting digital rights or infrastructure
    - Surveillance and privacy legislation
    - Notable system failures/downtime
    
    Use technical details where relevant (version numbers, CVEs, protocols).
    Present facts without opinion or sensationalism.
    Include concrete data points and statistics.
    
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
