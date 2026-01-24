import os
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import yaml

class ProperNewsReader:
    """Reads actual news files from your knowledge_base directory"""
    
    def __init__(self, base_path="./knowledge_base"):
        self.base_path = Path(base_path)
        self.news_dirs = self._find_news_directories()
        self.news_cache = {}
        self.last_refresh = None
        
    def _find_news_directories(self):
        """Find all news directories in the knowledge_base"""
        news_dirs = []
        
        # Look for news directories
        possible_paths = [
            self.base_path / "news",
            self.base_path / "news_briefs",
            self.base_path / "news" / "daily",
            self.base_path / "news" / "weekly",
            self.base_path / "daily",
            self.base_path / "weekly"
        ]
        
        for path in possible_paths:
            if path.exists() and path.is_dir():
                news_dirs.append(path)
                # print(f"✅ Found news directory: {path}")
        
        if not news_dirs:
            # print("❌ No news directories found!")
            # Create default structure
            (self.base_path / "news" / "daily").mkdir(parents=True, exist_ok=True)
            (self.base_path / "news" / "weekly").mkdir(parents=True, exist_ok=True)
            news_dirs = [self.base_path / "news"]
            # print(f"📁 Created default structure at {self.base_path / 'news'}")
        
        return news_dirs
    
    def scan_news_files(self):
        """Scan all news files and cache their content"""
        self.news_cache.clear()
        
        for news_dir in self.news_dirs:
            for file_path in news_dir.rglob("*.md"):
                try:
                    news_data = self._parse_news_file(file_path)
                    if news_data:
                        self._cache_news_data(news_data, str(file_path))
                except Exception as e:
                    print(f"⚠️ Error parsing {file_path}: {e}")
            
            # Also scan JSON and YAML files
            for ext in ["*.json", "*.yaml", "*.yml"]:
                for file_path in news_dir.rglob(ext):
                    try:
                        with open(file_path, 'r') as f:
                            if ext == "*.json":
                                data = json.load(f)
                            else:
                                data = yaml.safe_load(f)
                            
                            if data:
                                self._cache_news_data(data, str(file_path))
                    except Exception as e:
                        print(f"⚠️ Error reading {file_path}: {e}")
        
        self.last_refresh = datetime.now()
        # print(f"📰 Loaded {len(self.news_cache)} news items from {len(self.news_dirs)} directories")
    
    def _parse_news_file(self, file_path: Path) -> Optional[Dict]:
        """Parse a markdown news file into structured data"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract date from filename or content
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path.name)
        date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        
        # Parse markdown sections
        sections = {}
        current_section = None
        current_items = []
        
        for line in content.split('\n'):
            # Section header
            if line.startswith('## '):
                if current_section:
                    sections[current_section] = current_items
                current_section = line[3:].strip()
                current_items = []
            # Bullet point
            elif line.startswith('- ') and current_section:
                current_items.append(line[2:].strip())
            # Blank line (end of current items)
            elif not line.strip() and current_items:
                sections[current_section] = current_items
                current_section = None
                current_items = []
        
        if current_section and current_items:
            sections[current_section] = current_items
        
        if not sections:
            return None
        
        return {
            'date': date,
            'file': str(file_path),
            'sections': sections
        }
    
    def _cache_news_data(self, data: Dict, source: str):
        """Cache parsed news data with category mapping"""
        if isinstance(data, dict):
            if 'sections' in data:
                # Markdown format
                for section, items in data['sections'].items():
                    category = self._map_section_to_category(section)
                    for item in items:
                        self._add_to_cache(category, {
                            'text': item,
                            'date': data.get('date'),
                            'source': data.get('file', source),
                            'section': section
                        })
            else:
                # JSON/YAML format
                for category, items in data.items():
                    if isinstance(items, list):
                        for item in items:
                            self._add_to_cache(category, {
                                'text': item if isinstance(item, str) else str(item),
                                'source': source,
                                'date': datetime.now().strftime("%Y-%m-%d")
                            })
    
    def _map_section_to_category(self, section: str) -> str:
        """Map markdown sections to categories"""
        section_lower = section.lower()
        
        if any(word in section_lower for word in ['tech', 'ai', 'software', 'hardware', 'digital']):
            return 'technology'
        elif any(word in section_lower for word in ['politic', 'government', 'election', 'policy']):
            return 'politics'
        elif any(word in section_lower for word in ['security', 'cyber', 'hack', 'breach', 'cve']):
            return 'security'
        elif any(word in section_lower for word in ['business', 'economy', 'market', 'financial']):
            return 'business'
        elif any(word in section_lower for word in ['science', 'research', 'discovery']):
            return 'science'
        else:
            return 'general'
    
    def _add_to_cache(self, category: str, item: Dict):
        """Add item to category cache"""
        if category not in self.news_cache:
            self.news_cache[category] = []
        self.news_cache[category].append(item)
    
    def get_news_by_category(self, category: str, limit: int = 5) -> List[Dict]:
        """Get news items for a specific category"""
        if not self.news_cache or not self.last_refresh or (datetime.now() - self.last_refresh).seconds > 300:
            self.scan_news_files()
        
        category_lower = category.lower()
        
        # Find matching category
        matched_category = 'general'
        for cat in self.news_cache.keys():
            if cat in category_lower or category_lower in cat:
                matched_category = cat
                break
        
        items = self.news_cache.get(matched_category, [])
        
        # Sort by date if available (newest first)
        items_with_dates = []
        items_without_dates = []
        
        for item in items:
            if item.get('date'):
                items_with_dates.append(item)
            else:
                items_without_dates.append(item)
        
        # Sort by date descending
        items_with_dates.sort(key=lambda x: x['date'], reverse=True)
        
        all_items = items_with_dates + items_without_dates
        
        return all_items[:limit]
    
    def search_news(self, query: str, limit: int = 5) -> List[Dict]:
        """Search news by keyword"""
        if not self.news_cache:
            self.scan_news_files()
        
        query_lower = query.lower()
        results = []
        
        for category, items in self.news_cache.items():
            for item in items:
                if query_lower in item['text'].lower():
                    results.append(item)
        
        return results[:limit]
