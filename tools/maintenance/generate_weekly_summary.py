#!/usr/bin/env python3
"""
Weekly News Summary Generator
Summarizes a week's worth of archived news into a single weekly digest
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import re

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from dotenv import load_dotenv

load_dotenv()

class WeeklyNewsSummarizer:
    def __init__(self, gemini_api_key: str):
        """Initialize with Gemini API key"""
        if not genai:
            raise ImportError("google-generativeai not installed")
        
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-flash-latest')
        self.archive_dir = Path("./knowledge_base/news/archive")
        self.weekly_dir = Path("./knowledge_base/news/weekly")
        self.weekly_dir.mkdir(parents=True, exist_ok=True)
    
    def get_archived_weeks(self):
        """Find weeks with 7+ archived news files"""
        if not self.archive_dir.exists():
            return []
        
        # Get all archived briefs
        briefs = list(self.archive_dir.glob("news_brief_*.md"))
        
        # Group by week
        weeks = {}
        for brief in briefs:
            try:
                date_str = brief.stem.split('_')[-1]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                # Get week start (Monday)
                week_start = file_date - timedelta(days=file_date.weekday())
                week_key = week_start.strftime("%Y%m%d")
                
                if week_key not in weeks:
                    weeks[week_key] = []
                weeks[week_key].append(brief)
            except:
                continue
        
        # Return weeks with 7+ files
        complete_weeks = {}
        for week_key, files in weeks.items():
            if len(files) >= 7:
                complete_weeks[week_key] = sorted(files)
        
        return complete_weeks
    
    def generate_weekly_summary(self, week_files: list, week_start: str):
        """Generate weekly summary from daily briefs"""
        print(f"📅 Generating weekly summary for week of {week_start}...")
        
        # Read all briefs for the week
        combined_content = ""
        for i, file in enumerate(week_files[:7], 1):  # Limit to 7 days
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                combined_content += f"\n\n## DAY {i} ({file.stem.split('_')[-1]})\n{content}\n"
        
        # Create summary prompt
        prompt = f"""
Analyze this week's daily news briefs and create a comprehensive WEEKLY SUMMARY.

{combined_content[:15000]}  # Limit to avoid token overflow

Generate a structured weekly summary with these sections:

# WEEKLY NEWS SUMMARY: Week of {week_start}

## EXECUTIVE OVERVIEW
[3-4 sentences summarizing the most critical events of the week]

## TOP INCIDENTS
[5-7 most significant incidents across all categories, with brief descriptions]

## TECHNOLOGY TRENDS
- Major product releases
- Notable infrastructure changes
- Emerging technologies

## SECURITY LANDSCAPE
- Critical vulnerabilities (CVEs)
- Major breaches
- Attack trends

## POLITICAL & GEOPOLITICAL SHIFTS
- Key legislation
- International relations changes
- Policy impacts on tech

## NOTABLE QUOTES
[2-3 most significant quotes from the week]

## WEEK IN NUMBERS
- Total incidents tracked: X
- Critical vulnerabilities: Y
- Major outages: Z

---
**Generated**: {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}
**Coverage**: 7 days of news
**Format**: Weekly digest for long-term reference

RULES:
1. Synthesize, don't just list
2. Identify patterns and trends across the week
3. Highlight what matters for infrastructure/security
4. Keep technical details (CVEs, versions, etc.)
5. Maximum 40 bullet points total
"""
        
        # Generate using Gemini
        response = self.model.generate_content(prompt)
        summary = response.text.strip()
        
        return summary
    
    def save_weekly_summary(self, summary: str, week_start: str):
        """Save weekly summary"""
        filename = f"weekly_summary_{week_start}.md"
        filepath = self.weekly_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"✓ Saved weekly summary to: {filepath}")
    
    def run(self):
        """Generate summaries for all complete weeks"""
        print("🔍 Checking for complete weeks in archive...")
        
        complete_weeks = self.get_archived_weeks()
        
        if not complete_weeks:
            print("📭 No complete weeks (7+ days) found in archive yet")
            return
        
        print(f"📊 Found {len(complete_weeks)} complete week(s)")
        
        for week_start, files in complete_weeks.items():
            # Check if summary already exists
            summary_file = self.weekly_dir / f"weekly_summary_{week_start}.md"
            
            if summary_file.exists():
                print(f"✅ Weekly summary for {week_start} already exists")
                continue
            
            try:
                summary = self.generate_weekly_summary(files, week_start)
                self.save_weekly_summary(summary, week_start)
            except Exception as e:
                print(f"❌ Failed to generate summary for {week_start}: {e}")
        
        print(f"\n✅ Weekly summary generation complete")

if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ GEMINI_API_KEY environment variable not set")
        sys.exit(1)
    
    try:
        summarizer = WeeklyNewsSummarizer(api_key)
        summarizer.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
