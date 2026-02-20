#!/usr/bin/env python3
import urllib.request
from bs4 import BeautifulSoup
import datetime
from pathlib import Path
import random
import ollama

class LegacyNewsScraper:
    """Scrapes 68k.news (text-only Google News interface) to bypass Gemini quota"""
    def __init__(self):
        self.url = "http://68k.news/"
        self.knowledge_dir = Path("./knowledge_base/news/daily")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
    def fetch_and_parse(self):
        print(f"📡 Fetching raw news from {self.url}...")
        req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read()
        except Exception as e:
            print(f"❌ Failed to fetch news: {e}")
            return []

        soup = BeautifulSoup(html, 'html.parser')
        headlines = []
        current_source = 'Various Sources'
        
        # 68k.news puts headlines in <a> tags, inside <li> or <p> tags usually.
        # It's a very simple structure.
        for a_tag in soup.find_all('a'):
            text = a_tag.get_text(strip=True)
            link = a_tag.get('href', '')
            
            # Filter out UI links like "World", "US", "Business", etc.
            if len(text) > 25 and not text.lower() == '68k.news': 
                import re
                parts = re.split(r'\s+[-—–]\s+', text)
                if len(parts) > 1:
                    title = " - ".join(parts[:-1]).strip()
                    current_source = parts[-1].strip()
                else:
                    title = text.strip()
                    # Fallback to the last seen source for related/sub-headlines!
                
                headlines.append({'title': title, 'source': current_source, 'url': link})
                
        print(f"✅ Found {len(headlines)} raw headlines.")
        return headlines

    def categorize_headlines(self, headlines):
        """Simple keyword-based categorization to match Kaia's format"""
        categories = {
            'GENERAL_NEWS': [],
            'US_POLITICS': [],
            'GLOBAL_GEOPOLITICS': [],
            'CULTURE_AND_ENTERTAINMENT': [],
            'SCIENCE_AND_HEALTH': [],
            'BUSINESS_AND_ECONOMY': [],
            'TECHNOLOGY_AND_INFRASTRUCTURE': [],
            'SECURITY_INCIDENTS': [],
            'HACKER_CULTURE': []
        }
        
        # Very basic keyword matching
        for item in headlines:
            title_lower = item['title'].lower()
            
            if any(w in title_lower for w in ['hack', 'cve', 'breach', 'ransomware', 'cyber']):
                categories['SECURITY_INCIDENTS'].append(item)
            elif any(w in title_lower for w in ['ai', 'tech', 'software', 'apple', 'google', 'outage', 'internet']):
                categories['TECHNOLOGY_AND_INFRASTRUCTURE'].append(item)
            elif any(w in title_lower for w in ['market', 'stock', 'economy', 'amazon', 'tesla', 'bank']):
                categories['BUSINESS_AND_ECONOMY'].append(item)
            elif any(w in title_lower for w in ['space', 'science', 'health', 'study', 'medical', 'climate']):
                categories['SCIENCE_AND_HEALTH'].append(item)
            elif any(w in title_lower for w in ['movie', 'star', 'music', 'game', 'nintendo', 'sports']):
                categories['CULTURE_AND_ENTERTAINMENT'].append(item)
            elif any(w in title_lower for w in ['trump', 'biden', 'congress', 'senate', 'white house', 'election']):
                categories['US_POLITICS'].append(item)
            elif any(w in title_lower for w in ['war', 'russia', 'ukraine', 'china', 'iran', 'treaty', 'world']):
                categories['GLOBAL_GEOPOLITICS'].append(item)
            elif any(w in title_lower for w in ['leak', 'defcon', 'manifesto', 'anonymous']):
                categories['HACKER_CULTURE'].append(item)
            else:
                categories['GENERAL_NEWS'].append(item)
                
        return categories

    def generate_executive_summary_text(self, categorized):
        top_headlines = []
        for cat in ['US_POLITICS', 'GLOBAL_GEOPOLITICS', 'BUSINESS_AND_ECONOMY', 'TECHNOLOGY_AND_INFRASTRUCTURE']:
            if categorized.get(cat):
                top_headlines.append(categorized[cat][0]['title'])
        
        if top_headlines:
            summary = "Top stories today: " + "; ".join(top_headlines[:3]) + "."
            return summary
        else:
            return "Automated scrape from 68k.news. High-volume raw feed."

    def generate_brief(self, categorized, exec_summary):
        """Format the scraped data into the markdown brief"""
        lines = [f"# NEWS_BRIEF: {self.today}\n"]
        lines.append("## EXECUTIVE_SUMMARY")
        lines.append(f"{exec_summary}\n")
        
        for category, items in categorized.items():
            lines.append(f"## {category}")
            if not items:
                lines.append("- No specific news found for this category today.")
            else:
                # Randomly sample up to 5 items per category so we don't spam RAG
                sampled = random.sample(items, min(5, len(items)))
                for item in sampled:
                    lines.append(f"- {item['title']} - *{item['source']}*")
            lines.append(f"- QUOTE: \"Data extracted systematically from 68k text interface.\" - Automated Scraper\n")
            
        lines.append(f"---\n**Generated**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}")
        return "\n".join(lines)
        
    def save_brief(self, brief_content):
        filename = f"news_brief_{self.today.replace('-', '')}.md"
        filepath = self.knowledge_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(brief_content)
        print(f"💾 Saved scraped brief to {filepath}")
        return filepath

    def generate_short_summary(self, full_brief):
        """Creates a fast, system-generated summary file without relying on slow local LLMs"""
        print(f"⚠️ Bypassing Ollama to prevent inference hanging, saving raw bullets.")
        summary_file = self.knowledge_dir / f"news_summary_{self.today.replace('-', '')}.md"
        with open(summary_file, 'w', encoding='utf-8') as f:
            lines = full_brief.split('\n')
            bullet_lines = [line for line in lines if line.strip().startswith('- ')]
            
            # Write a very dense version of the brief for RAG
            f.write(f"# QUICK REFERENCE: {self.today}\n\n")
            f.write("Scraped from 68k.news. High volume bullet points:\n")
            f.write('\n'.join(bullet_lines[:12]))
            print(f"✨ Created fast summary at {summary_file}")

    def run(self):
        headlines = self.fetch_and_parse()
        if not headlines:
            return
            
        categorized = self.categorize_headlines(headlines)
        exec_summary = self.generate_executive_summary_text(categorized)
        brief = self.generate_brief(categorized, exec_summary)
        
        self.save_brief(brief)
        self.generate_short_summary(brief)
        print("🎉 68k.news Scraping Complete!")

if __name__ == "__main__":
    try:
        # beautifulsoup4 is required
        import bs4
    except ImportError:
        print("⚠️ BeautifulSoup4 is required. Please run: pip install beautifulsoup4")
        import sys
        sys.exit(1)
        
    scraper = LegacyNewsScraper()
    scraper.run()
