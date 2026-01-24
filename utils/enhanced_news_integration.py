import os
import json
import yaml
from datetime import datetime
import aiohttp
import asyncio
import random

class EnhancedNewsHandler:
    """Enhanced news integration with real data sources"""
    
    def __init__(self, config_path="./config/news_sources.yaml"):
        self.config_path = config_path
        self.sources = self.load_sources()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    def load_sources(self):
        """Load news sources configuration"""
        sources = {
            "rss_feeds": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
                "https://feeds.bbci.co.uk/news/rss.xml",
                "https://hnrss.org/frontpage",
                "https://www.reddit.com/r/worldnews/.rss",
                "https://www.theguardian.com/world/rss"
            ],
            "api_sources": {
                "newsapi": {
                    "enabled": False,  # Set to True with API key
                    "endpoint": "https://newsapi.org/v2/top-headlines",
                    "categories": ["technology", "science", "business", "entertainment", "health"]
                }
            },
            "local_sources": [
                "./knowledge_base/news_briefs/",
                "./news_digests/weekly/"
            ]
        }
        
        # Load custom config if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    custom_config = yaml.safe_load(f)
                    if custom_config:
                        sources.update(custom_config)
            except Exception as e:
                print(f"Error loading config: {e}")
                
        return sources
    
    async def fetch_news(self, category=None, limit=5):
        """Fetch fresh news from multiple sources"""
        news_items = []
        
        # 1. Check local knowledge base first
        local_news = self.get_local_news(category, limit)
        news_items.extend(local_news)
        
        # 2. If insufficient, try to fetch fresh (simulated/sample for now if no API)
        if len(news_items) < limit:
            fresh_news = await self.fetch_fresh_news(category, limit - len(news_items))
            news_items.extend(fresh_news)
        
        # 3. Format for response (just return items here, formatting happens later or via helper)
        return news_items[:limit]
    
    def get_local_news(self, category=None, limit=5):
        """Get news from local knowledge base"""
        news_items = []
        
        # Check news directories
        news_dirs = ["./knowledge_base/news_briefs", "./knowledge_base/news/daily"]
        
        for news_dir in news_dirs:
            if os.path.exists(news_dir):
                for file in os.listdir(news_dir):
                    if file.endswith(('.md', '.json', '.yaml')):
                        file_path = os.path.join(news_dir, file)
                    try:
                        if file.endswith('.json'):
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                                # Handle different JSON structures
                                if 'categories' in data:
                                    # Structure from refresh_news.py
                                    cat_data = data['categories']
                                    if category and category.lower() in cat_data:
                                        news_items.extend(cat_data[category.lower()])
                                    elif not category:
                                        for cat_items in cat_data.values():
                                            news_items.extend(cat_items)
                                elif 'items' in data:
                                    # Simple list structure
                                    items = data['items']
                                    for item in items:
                                        if isinstance(item, dict) and 'items' in item:
                                            # Handle nested structure from FastNewsRetriever
                                            cat = item.get('category', '').lower()
                                            if not category or cat == category.lower() or category == 'general':
                                                # These are strings in a list
                                                for subitem in item['items']:
                                                    news_items.append({'title': subitem, 'source': 'Local Cache'})
                                        elif category:
                                            # Filter if items have category field
                                            if isinstance(item, dict) and item.get('category', '').lower() == category.lower():
                                                news_items.append(item)
                                        else:
                                            news_items.append(item)
                                elif isinstance(data, list):
                                    news_items.extend(data)
                                    
                    except Exception as e:
                        print(f"Error reading {file}: {e}")
        
        return news_items[:limit]
    
    async def fetch_fresh_news(self, category=None, limit=3):
        """Fetch fresh news from external sources"""
        # This would be implemented with actual API calls
        # For now, return enhanced sample data
        return self.get_enhanced_sample_news(category, limit)
    
    def get_enhanced_sample_news(self, category=None, limit=3):
        """Enhanced sample news with more detail"""
        sample_news = {
            "technology": [
                {
                    "title": "OpenAI releases GPT-5 with 40% reduction in hallucinations",
                    "source": "TechCrunch",
                    "date": "2026-01-23",
                    "summary": "New model shows significant improvements in factual accuracy and reasoning capabilities.",
                    "url": "https://techcrunch.com/gpt5-release"
                },
                {
                    "title": "Quantum computing milestone: 1000-qubit processor demonstrated",
                    "source": "Nature",
                    "date": "2026-01-22", 
                    "summary": "Researchers achieve error correction in large-scale quantum system.",
                    "url": "https://nature.com/quantum-breakthrough"
                }
            ],
            "politics": [
                {
                    "title": "Digital Oversight Act moves to Senate vote",
                    "source": "Reuters",
                    "date": "2026-01-23",
                    "summary": "Controversial bill requiring software escrow for critical infrastructure faces bipartisan scrutiny.",
                    "url": "https://reuters.com/digital-oversight"
                }
            ],
            "security": [
                {
                    "title": "Critical Redis vulnerability (CVE-2026-0115) actively exploited",
                    "source": "BleepingComputer",
                    "date": "2026-01-23",
                    "summary": "RCE vulnerability in Redis 7.x and earlier leads to global scanning activity.",
                    "url": "https://bleepingcomputer.com/redis-cve"
                }
            ],
            "business": [
                 {
                    "title": "Global markets react to new AI regulations",
                    "source": "Bloomberg",
                    "date": "2026-01-23",
                    "summary": "Tech stocks see volatility as EU announces strict AI compliance measures.",
                    "url": "https://bloomberg.com/ai-regulations"
                }
            ],
            "science": [
                {
                    "title": "Mars colony prototype completes 1-year isolation test",
                    "source": "Space.com",
                    "date": "2026-01-22",
                    "summary": "Six-person crew successfully exits simulated habitat in Arizona desert.",
                    "url": "https://space.com/mars-simulation"
                }
            ]
        }
        
        if category and category.lower() in sample_news:
            return sample_news[category.lower()][:limit]
        
        # Return mixed if no category or category not found
        all_news = []
        for cat in sample_news.values():
            all_news.extend(cat)
        return all_news[:limit]
    
    def format_news_items(self, news_items, category=None):
        """Format news items for Kaia's conversational style"""
        if not news_items:
            return None
        
        if category in ["politics", "security"]:
            # Conversational format
            lines = [f"On the {category.lower()} front:"]
            for i, item in enumerate(news_items, 1):
                if isinstance(item, dict):
                    lines.append(f"  • {item.get('title', 'Unknown')}")
                    if 'summary' in item:
                        lines.append(f"    {item['summary']}")
                else:
                    lines.append(f"  • {item}")
            
            # Add Kaia's commentary
            commentary = self.get_commentary(category, len(news_items))
            lines.append(f"\n{commentary}")
            
            return "\n".join(lines)
        else:
            # List format with some commentary
            lines = [f"Here's what I'm seeing in {category or 'general'}:"]
            for item in news_items:
                if isinstance(item, dict):
                    lines.append(f"• {item.get('title', 'Unknown')}")
                else:
                    lines.append(f"• {item}")
            
            return "\n".join(lines)
    
    def get_commentary(self, category, item_count):
        """Get Kaia-style commentary based on category"""
        commentaries = {
            "politics": [
                f"Politics... always a mess. {item_count} things to worry about, and that's just today.",
                f"Another day in the circus. {item_count} new developments to track.",
                f"It's always something. {item_count} new fires to put out."
            ],
            "security": [
                f"Vulnerabilities everywhere. {item_count} new reasons to update your systems.",
                f"The attack surface keeps expanding. {item_count} new entry points.",
                f"Constant vigilance. {item_count} new threats this week."
            ],
            "technology": [
                f"Progress never sleeps. {item_count} new developments changing everything.",
                f"The future arrives daily. {item_count} breakthroughs to process.",
                f"Always something new. {item_count} innovations shifting the landscape."
            ]
        }
        
        return random.choice(commentaries.get(category.lower(), ["Keep an eye on this."]))
