#!/usr/bin/env python3
"""
tools/maintenance/scrape_tech_news.py
Aggregates developer-centric news and AI updates into Kaia's general knowledge base.
"""
import os
import json
import urllib.request
import xml.etree.ElementTree as ET
import datetime
from pathlib import Path
import re
import sys

# Try importing ollama
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

class TechNewsScraper:
    def __init__(self):
        self.output_dir = Path("./knowledge_base/documents/tech_updates")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # High-signal developer and AI keywords
        self.keywords = [
            "llm", "deepseek", "openai", "claude", "gemini", "gemma", "ollama",
            "nvidia", "gpu", "tpu", "h100", "b200", "llama-index", "langchain",
            "pytorch", "agentic", "antigravity", "cursor", "copilot", "rust",
            "cybersecurity", "quantum", "machine learning", "silicon", "transformer"
        ]
        
    def fetch_hacker_news(self, limit=40) -> list:
        """Fetches top Hacker News items and filters them by keyword"""
        stories = []
        try:
            print("📡 Fetching Hacker News top stories...")
            top_ids_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            req = urllib.request.Request(top_ids_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                top_ids = json.loads(r.read().decode())[:limit]
                
            for item_id in top_ids:
                item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                try:
                    item_req = urllib.request.Request(item_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(item_req, timeout=5) as ir:
                        item = json.loads(ir.read().decode())
                        if not item:
                            continue
                        title = item.get("title", "")
                        url = item.get("url", "")
                        score = item.get("score", 0)
                        
                        # Match keywords or check if it has a very high score (high signal)
                        title_lower = title.lower()
                        if any(kw in title_lower for kw in self.keywords) or score > 200:
                            stories.append({
                                "title": title,
                                "url": url,
                                "source": "Hacker News",
                                "score": score
                            })
                except Exception as e:
                    # Silently skip single story errors to keep loop moving
                    continue
        except Exception as e:
            print(f"❌ HN fetch failed: {e}")
        print(f"✅ Gathered {len(stories)} stories from Hacker News.")
        return stories

    def fetch_rss_feeds(self) -> list:
        """Fetches entries from developer-focused RSS feeds"""
        feeds = {
            "Ars Technica": "https://feeds.feedburner.com/arstechnica/index",
            "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
            "Wired Tech": "https://www.wired.com/feed/category/gear/latest/rss"
        }
        entries = []
        for name, url in feeds.items():
            try:
                print(f"📡 Fetching RSS from {name}...")
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as r:
                    xml_data = r.read()
                    root = ET.fromstring(xml_data)
                    
                    # Handles standard RSS <item> tags
                    for item in root.findall(".//item"):
                        title_elem = item.find("title")
                        link_elem = item.find("link")
                        desc_elem = item.find("description")
                        
                        title = title_elem.text if title_elem is not None else ""
                        link = link_elem.text if link_elem is not None else ""
                        desc_text = desc_elem.text if desc_elem is not None else ""
                        
                        if not title:
                            continue
                            
                        # Clean HTML from description
                        desc_clean = re.sub("<[^<]+?>", "", desc_text).strip()
                        combined = (title + " " + desc_clean).lower()
                        
                        if any(kw in combined for kw in self.keywords):
                            entries.append({
                                "title": title,
                                "url": link,
                                "source": name,
                                "summary": desc_clean[:250]
                            })
            except Exception as e:
                print(f"❌ RSS {name} failed: {e}")
        print(f"✅ Gathered {len(entries)} items from RSS feeds.")
        return entries

    def generate_executive_summary(self, markdown_body: str) -> str:
        """Generates a 3-sentence executive summary using local Ollama model if available"""
        if not HAS_OLLAMA:
            print("⚠️ Ollama package is not available. Skipping LLM summary.")
            return "Daily technical digest tracking developer movements, AI releases, and infrastructure events."
            
        prompt = f"""
        Analyze this raw technical news feed and generate a professional, high-density 3-sentence executive summary.
        Do not add greeting, introduction, or conversational filler.
        
        FEED BODY:
        {markdown_body[:4000]}
        
        Requirements:
        1. Keep the output to exactly 3 concise, factual sentences.
        2. Focus on AI developments, tool announcements, and major infrastructure releases.
        3. Do not invent any facts not present in the body.
        """
        
        try:
            print("🧠 Generating tech digest summary via gemma3:12b...")
            response = ollama.chat(
                model='gemma3:12b',
                messages=[
                    {'role': 'system', 'content': 'You compile brief summaries of technical development digests.'},
                    {'role': 'user', 'content': prompt}
                ]
            )
            summary = response['message']['content'].strip()
            if summary:
                # Remove any leading conversational tags if leaked
                summary = re.sub(r'^(Here is a summary:|Here is the executive summary:|Executive Summary:)\s*', '', summary, flags=re.IGNORECASE)
                return summary
        except Exception as e:
            print(f"⚠️ Ollama summarization failed: {e}. Falling back to default header.")
            
        # Deterministic fallback
        return "Daily technical digest tracking developer updates, AI model releases, and core infrastructure events."

    def generate_digest_markdown(self, items: list) -> tuple:
        """Builds a structured markdown brief of the collected items"""
        body_lines = ["## Key Tech & AI Updates\n"]
        
        seen_titles = set()
        count = 0
        for item in items:
            title = item["title"].strip()
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            
            body_lines.append(f"### {title}")
            body_lines.append(f"* **Source**: {item['source']}")
            if item.get("url"):
                body_lines.append(f"* **Reference**: {item['url']}")
            if item.get("summary"):
                body_lines.append(f"* **Details**: {item['summary'].strip()}")
            elif item.get("score"):
                body_lines.append(f"* **Details**: Highly discussed item (Score: {item['score']} points)")
            body_lines.append("")
            count += 1
            if count >= 20:  # Prevent oversized files
                break
                
        body_content = "\n".join(body_lines)
        
        # Generate summary using the formatted body content
        exec_summary = self.generate_executive_summary(body_content)
        
        header_lines = [
            f"# Tech Digest: {self.today}",
            "**Document Type**: Technical Summary",
            f"**Ingested**: {datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            "## Executive Summary",
            f"{exec_summary}\n",
            "---"
        ]
        
        full_markdown = "\n".join(header_lines) + "\n\n" + body_content
        return full_markdown, count

    def run(self):
        hn_items = self.fetch_hacker_news()
        rss_items = self.fetch_rss_feeds()
        all_items = hn_items + rss_items
        
        if not all_items:
            print("📭 No relevant tech news items found today.")
            return
            
        markdown_content, count = self.generate_digest_markdown(all_items)
        output_file = self.output_dir / f"tech_digest_{self.today.replace('-', '')}.md"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
            
        print(f"💾 Saved {count} technical digest entries to {output_file}")

if __name__ == "__main__":
    scraper = TechNewsScraper()
    scraper.run()
