import os
import json
import random
from datetime import datetime, timedelta
from collections import defaultdict

class FastNewsRetriever:
    """Fast news retrieval without LLM classification"""
    
    def __init__(self, news_dir="./knowledge_base/news_briefs"):
        self.news_dir = news_dir
        self.news_cache = defaultdict(list)
        self.last_cache_refresh = None
        
        # News categories for quick matching
        self.categories = {
            "technology": ["ai", "tech", "software", "hardware", "internet", "cyber", "digital"],
            "politics": ["election", "government", "policy", "senate", "congress", "president"],
            "business": ["market", "stock", "economy", "company", "corporate", "financial"],
            "security": ["hack", "breach", "cyber", "attack", "vulnerability", "cve", "ransomware"],
            "science": ["research", "discovery", "study", "scientific", "breakthrough"],
            "entertainment": ["movie", "tv", "celebrity", "music", "game", "streaming"]
        }
        
        self.load_news()
    
    def load_news(self):
        """Load news from files"""
        if not os.path.exists(self.news_dir):
            os.makedirs(self.news_dir)
            
        # Check for news files
        news_files = [f for f in os.listdir(self.news_dir) if f.endswith(('.md', '.json'))]
        
        if not news_files:
            # Create sample news if none exist
            self.create_sample_news()
            news_files = os.listdir(self.news_dir)
        
        for news_file in news_files:
            filepath = os.path.join(self.news_dir, news_file)
            try:
                if news_file.endswith('.json'):
                    with open(filepath, 'r') as f:
                        news_data = json.load(f)
                        self._categorize_news(news_data)
                elif news_file.endswith('.md'):
                    news_data = self._parse_md_news(filepath)
                    self._categorize_news(news_data)
            except Exception as e:
                print(f"⚠️ Error loading {news_file}: {e}")
        
        self.last_cache_refresh = datetime.now()
    
    def _parse_md_news(self, filepath):
        """Parse markdown news file"""
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Simple parsing for markdown
        lines = content.split('\n')
        news_items = []
        current_item = {}
        
        for line in lines:
            if line.startswith('## '):
                if current_item:
                    news_items.append(current_item)
                    current_item = {}
                current_item['category'] = line[3:].strip()
            elif line.startswith('- '):
                if 'items' not in current_item:
                    current_item['items'] = []
                current_item['items'].append(line[2:].strip())
        
        if current_item:
            news_items.append(current_item)
        
        return {'items': news_items, 'source': filepath}
    
    def _categorize_news(self, news_data):
        """Categorize news items"""
        if 'items' in news_data:
            for item in news_data['items']:
                # Handle nested items structure from markdown parsing
                if isinstance(item, dict) and 'items' in item:
                    for subitem in item['items']:
                        self._add_to_cache(subitem, item.get('category'))
                else:
                    self._add_to_cache(item)

    def _add_to_cache(self, item, explicit_category=None):
        """Add single item to cache with categorization"""
        text = str(item).lower()
        
        # Use explicit category if provided and valid
        if explicit_category:
            cat_lower = explicit_category.lower()
            for known_cat in self.categories.keys():
                if known_cat in cat_lower:
                    self.news_cache[known_cat].append(item)
                    return

        # Find matching category from text
        matched = False
        for category, keywords in self.categories.items():
            if any(keyword in text for keyword in keywords):
                self.news_cache[category].append(item)
                matched = True
        
        # Default category
        if not matched:
            self.news_cache['general'].append(item)
    
    def get_news_by_category(self, category, limit=5):
        """Get news by category"""
        category_lower = category.lower()
        
        # Find best matching category
        best_match = 'general'
        for cat in self.categories.keys():
            if cat in category_lower or category_lower in cat:
                best_match = cat
                break
        
        news_items = self.news_cache.get(best_match, [])
        
        if not news_items:
            # Fallback to any news
            all_news = []
            for cat_news in self.news_cache.values():
                all_news.extend(cat_news)
            news_items = all_news
        
        # Random selection for variety
        if len(news_items) > limit:
            return random.sample(news_items, limit)
        return news_items
    
    def create_sample_news(self):
        """Create sample news if none exist"""
        sample_news = {
            "technology": [
                "OpenAI announces GPT-5 with 40% fewer hallucinations",
                "Quantum computing breakthrough: 500-qubit processor achieves error correction",
                "Apple unveils Vision Pro 2 with neural interface",
                "Tesla's Optimus robot now performing warehouse tasks",
                "Microsoft releases Windows 13 with integrated AI assistant"
            ],
            "politics": [
                "EU passes Digital Services Act 2.0 with stricter AI regulations",
                "US-China trade talks resume amid semiconductor tensions",
                "Brazil announces major investment in renewable energy infrastructure",
                "India's digital currency sees 300% adoption in first year",
                "African Union establishes continental AI ethics framework"
            ],
            "business": [
                "Stock markets hit record highs as AI companies surge",
                "Amazon acquires robotics startup for $2.3 billion",
                "Cryptocurrency market rebounds with new regulatory clarity",
                "Global supply chain disruptions easing, says WTO report",
                "Remote work adoption stabilizes at 45% of workforce"
            ],
            "security": [
                "Major data breach exposes 50 million user records",
                "New phishing campaign uses deepfake CEO audio",
                "Critical vulnerability patched in Apache web servers",
                "Ransomware group targets healthcare providers across Europe",
                "Zero-day in popular VPN software actively exploited"
            ]
        }
        
        # Save to file
        import json
        filename = os.path.join(self.news_dir, "sample_news.json")
        with open(filename, 'w') as f:
            json.dump({'items': [{'category': k, 'items': v} for k, v in sample_news.items()]}, f, indent=2)
        
        # Also load into cache
        for category, items in sample_news.items():
            self.news_cache[category].extend(items)
