import asyncio
import json
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collections import defaultdict
import re
import hashlib
import yaml
from pathlib import Path
from utils.infrastructure.logging.kaia_logger import log_info

class NewsManager:
    """Unified news manager for scanning, parsing, and retrieving news (Consolidated)"""
    
    def __init__(self, base_path="./knowledge_base/news"):
        self.base_path = Path(base_path)
        self.news_cache = defaultdict(list)
        self.last_refresh = None
        self._lock = threading.Lock()
        self.categories = {
            "technology": ["ai", "tech", "software", "hardware", "internet", "cyber", "digital", "chip", "tsmc", "nvidia", "cloud", "outage", "infrastructure", "isp"],
            "politics": ["election", "government", "policy", "senate", "congress", "president", "diplomatic", "legislation", "treaty", "ndaa"],
            "business": ["market", "stock", "economy", "company", "corporate", "financial", "merger", "acquisition", "crypto", "bitcoin", "blockchain"],
            "security": ["hack", "breach", "cyber", "attack", "vulnerability", "cve", "ransomware", "exploit", "patch", "leak", "compromise"],
            "science": ["research", "discovery", "study", "scientific", "breakthrough", "medical", "space", "astronomy", "nasa", "spacex", "environment"],
            "culture": ["movie", "tv", "celebrity", "music", "game", "art", "book", "fashion", "travel", "entertainment", "society", "trend"],
            "hacker": ["lapsus", "anonymous", "apt", "manifesto", "defcon", "blackhat", "ctf", "hacker", "cyberwarfare", "hacktivism", "exploit"]
        }
        self._ensure_base_path()
        # self.refresh() # DISABLED at boot for stabilization

    def _ensure_base_path(self):
        """Ensure the news directory exists"""
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)
            (self.base_path / "daily").mkdir(exist_ok=True)

    def refresh(self):
        """Scan and parse all news files"""
        with self._lock:
            self.news_cache.clear()
            
            # Scan all supported files in the news directory recursively
            for ext in ["*.md", "*.json", "*.yaml", "*.yml"]:
                for file_path in self.base_path.rglob(ext):
                    try:
                        if ext == "*.md":
                            self._parse_md_file(file_path)
                        elif ext == "*.json":
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                                self._cache_structured_data(data, str(file_path))
                        else: # yaml/yml
                            with open(file_path, 'r') as f:
                                data = yaml.safe_load(f)
                                self._cache_structured_data(data, str(file_path))
                    except Exception as e:
                        # Use print here as logger might not be initialized or passed
                        log_warning(f"Error parsing {file_path}: {e}")
            
            self.last_refresh = datetime.now()

    def _parse_md_file(self, file_path: Path):
        """Parse markdown news file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract date from filename or content
        # Supports YYYY-MM-DD and YYYYMMDD
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})|(\d{8})', file_path.name)
        if date_match:
            date_str = date_match.group(0)
            if len(date_str) == 8: # YYYYMMDD
                date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                date = date_str
        else:
            date = datetime.now().strftime("%Y-%m-%d")
        
        current_section = None
        current_items = []
        
        for line in content.split('\n'):
            stripped = line.strip()
            if not stripped: continue
            
            if stripped.startswith('## '):
                # Save previous section if it has items
                if current_section and current_items:
                    self._add_to_cache(current_section, current_items, date, str(file_path))
                
                current_section = stripped[3:].strip()
                
                # Skip truly irrelevant metadata sections
                if current_section.upper() in ['SOURCES', 'FAILURE_METRICS', 'QUOTES']:
                    current_section = None
                    
                current_items = []
            elif current_section:
                # SKIP metadata and boilerplate
                skip_keywords = ['QUOTE:', 'Generated:', 'RULES:', 'TARGET SOURCES:', '---', '**Generated**:']
                if any(stripped.startswith(kw) for kw in skip_keywords):
                    continue
                
                # Also skip specific boilerplate phrases
                if "Search for and compile" in stripped or "You are a news aggregator" in stripped:
                    continue
                    
                # Add as an item if it's not a header level 1 or 2
                if not stripped.startswith('#'):

                    # Handle multiple bullet styles or plain text
                    item_text = ""
                    if stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('• '):
                        item_text = stripped[2:].strip()
                    else:
                        item_text = stripped.strip()
                    
                    if item_text and len(item_text) > 10: # Minimum length to avoid junk
                        current_items.append(item_text)
        
        # Add the final section
        if current_section and current_items:
            self._add_to_cache(current_section, current_items, date, str(file_path))

    def _cache_structured_data(self, data: Dict, source: str):
        """Cache JSON/YAML news data"""
        if not isinstance(data, dict): return
        
        # Handle different common structures
        if 'categories' in data:
            for cat, items in data['categories'].items():
                self._add_to_cache(cat, items, data.get('date'), source)
        elif 'items' in data:
            for item in data['items']:
                if isinstance(item, dict) and 'category' in item and 'items' in item:
                    self._add_to_cache(item['category'], item['items'], data.get('date'), source)
                else:
                    self._add_to_cache('general', [item], data.get('date'), source)
        else:
            # Direct category mapping
            for cat, items in data.items():
                if isinstance(items, list):
                    self._add_to_cache(cat, items, None, source)

    def _add_to_cache(self, section: str, items: List, date: str = None, source: str = None):
        """Add items to cache with category mapping"""
        category = self._map_to_category(section)
        if not category:
            return
            
        for item in items:
            text = ""
            item_date = date
            
            if isinstance(item, dict):
                # Try to find content in common keys
                text = item.get('text') or item.get('summary') or item.get('title') or item.get('content') or str(item)
                item_date = item.get('date') or item_date
            else:
                text = str(item)
            
            # DEDUPLICATION: Check if this text already exists in this category
            if any(existing['text'] == text for existing in self.news_cache[category]):
                continue
                
            self.news_cache[category].append({
                'text': text,
                'date': item_date or datetime.now().strftime("%Y-%m-%d"),
                'source': source or 'Unknown',
                'original_section': section
            })

    def _map_to_category(self, section: str) -> str:
        """Map a section name or text to a known category"""
        section_upper = section.upper()
        # Metadata to skip completely
        if section_upper in ['SOURCES', 'FAILURE_METRICS', 'QUOTES']:
            return None
            
        # High-level overview maps to 'general'
        if section_upper in ['EXECUTIVE_SUMMARY', 'HEADLINES', 'SUMMARY']:
            return 'general'

        section_lower = section.lower()
        
        # Direct section name mappings (from updated news prompt)
        direct_mappings = {
            'general_news': 'general',
            'general_tech_and_society': 'general',
            'us_politics': 'politics',
            'global_geopolitics': 'politics',
            'culture_and_entertainment': 'culture',
            'science_and_health': 'science',
            'business_and_economy': 'business',
            'technology': 'technology', 
            'technology_and_infrastructure': 'technology',
            'security_incidents': 'security',
            'data_breaches': 'security',
            'ransomware': 'security',
            'tech_outages': 'technology',
            'hacker_culture': 'hacker',
            'hacker_culture_and_cyberwarfare': 'hacker',
        }
        
        # Check direct section name match first
        section_key = section_lower.replace(' ', '_').replace('-', '_')
        if section_key in direct_mappings:
            return direct_mappings[section_key]
        
        # Prioritize hacker if mentioned
        if 'hacker' in section_lower or 'cyberwarfare' in section_lower:
            return 'hacker'
            
        # Prioritize culture if explicitly mentioned in section name
        if 'culture' in section_lower or 'entertainment' in section_lower:
            return 'culture'
        
        # Politics mapping
        if 'politic' in section_lower or 'geopolitic' in section_lower or 'congress' in section_lower or 'election' in section_lower:
            return 'politics'
        
        # Prioritize science if mentioned (often combined as Science/Culture)
        if 'science' in section_lower:
            return 'science'
            
        # Intelligence/AI mapping
        if 'intelligence' in section_lower or 'ai' in section_lower:
            return 'technology'
            
        # Infrastructure mapping
        if 'infrastructure' in section_lower:
            return 'technology'

        for cat, keywords in self.categories.items():
            if cat in section_lower or any(kw in section_lower for kw in keywords):
                return cat
        return 'general'

    async def get_news_async(self, category: str = None, limit: int = 5) -> List[Dict]:
        """Asynchronously retrieve news items, refreshing if stale."""
        # Check if refresh is needed
        if not self.last_refresh or (datetime.now() - self.last_refresh).total_seconds() > 300:
            log_info("News cache stale, refreshing in background thread...")
            await asyncio.to_thread(self.refresh)
            
        return self.get_news(category, limit)

    def get_news(self, category: str = None, limit: int = 5) -> List[Dict]:
        """Retrieve news items from cache. 
        
        Note: This is now a 'light' wrapper around the cache. 
        The automatic refresh logic remains for legacy synchronous callers, 
        but async callers should use get_news_async.
        """
        if not self.last_refresh or (datetime.now() - self.last_refresh).total_seconds() > 300:
            # If we're in an event loop, we should avoid blocking refresh.
            # But for legacy sync, we have to.
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # If we're in the loop and it's stale, we just return what we have
                    # and let get_news_async handle the refresh if it was called.
                    pass
                else:
                    with self._lock:
                        self.refresh()
            except RuntimeError:
                with self._lock:
                    self.refresh()
            
        category_lower = (category or 'general').lower()
        
        # Find best matching category
        matched_cat = None
        
        # SPECIAL REDIRECTS
        if category_lower == "hacking":
            category_lower = "hacker"
        
        # Check if it matches a known category first
        for cat in self.categories.keys():
            if cat == category_lower or cat in category_lower or category_lower in cat:
                matched_cat = cat
                break
        
        # If specifically requested a category that doesn't exist, return empty
        if category and not matched_cat:
            return []
            
        if not matched_cat:
            matched_cat = 'general'
        
        with self._lock:
            items = self.news_cache.get(matched_cat, [])
            
            # If we found a category but it's empty, return empty
            if not items:
                return []

            # PRIORITIZE RECENCY: 
            # 1. Get today's date
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # 2. Separate today's news from older news
            today_items = [i for i in items if i.get('date') == today_str]
            older_items = [i for i in items if i.get('date') != today_str]
            
            # 3. Sort older items by date descending
            older_items.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            # 4. Build final list: today's news first, then fill with older news
            all_prioritized = today_items + older_items
            
            # 5. Return latest items up to limit
            return all_prioritized[:limit]

class NewsRetrievalEnhancer:
    """Advanced news retrieval system for Kaia"""
    
    def __init__(self, max_news_per_query: int = 8, days_of_freshness: int = 7):
        self.max_news_per_query = max_news_per_query
        self.days_of_freshness = days_of_freshness
        self.memory_path = Path("memory/mentioned_news.json")
        self.mentioned_news_cache = defaultdict(set)  # user_id -> set of news IDs
        self.news_categories = {
            'tech': ['tsmc', 'nvidia', 'azure', 'amd', 'intel', 'chip', 'hardware'],
            'security': ['cve', 'breach', 'zero-day', 'vulnerability', 'patch', 'exploit'],
            'ai': ['ai act', 'regulation', 'llm', 'model', 'training', 'inference'],
            'business': ['startup', 'funding', 'acquisition', 'merger', 'layoff'],
            'science': ['discovery', 'research', 'study', 'breakthrough'],
            'gaming': ['game', 'console', 'steam', 'playstation', 'xbox']
        }
        self.load_mentioned_news()

    def save_mentioned_news(self):
        """Save mentioned news cache to disk"""
        try:
            # Convert sets to lists for JSON serialization
            serializable_cache = {user_id: list(news_ids) for user_id, news_ids in self.mentioned_news_cache.items()}
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_path, 'w') as f:
                json.dump(serializable_cache, f)
        except Exception as e:
            log_warning(f"Error saving mentioned news: {e}")

    def load_mentioned_news(self):
        """Load mentioned news cache from disk"""
        try:
            if self.memory_path.exists():
                with open(self.memory_path, 'r') as f:
                    data = json.load(f)
                    # Convert lists back to sets
                    self.mentioned_news_cache = defaultdict(set, {user_id: set(news_ids) for user_id, news_ids in data.items()})
        except Exception as e:
            log_warning(f"Error loading mentioned news: {e}")
    
    def enhance_news_query(self, original_query: str, user_id: str = None) -> str:
        """Enhance news queries for better retrieval"""
        query = original_query.lower()
        
        # Add temporal context
        if 'recent' in query or 'latest' in query or 'this week' in query:
            time_context = f" from the last {self.days_of_freshness} days"
            if 'week' in query:
                time_context = " from this week"
            query += time_context
        
        # Add diversity trigger
        if 'more' in query or 'else' in query or 'other' in query:
            query += " different diverse topics"
        
        if 'interesting' in query or 'intresting' in query:
            query += " unusual unexpected surprising"
        
        return query
    
    def diversify_news_results(self, news_items: List[Dict], user_id: str = None) -> List[Dict]:
        """Ensure diverse news topics and avoid repetition"""
        if not news_items:
            return []
        
        # Group by category
        categorized = defaultdict(list)
        for item in news_items:
            category = self._categorize_news(item.get('content', ''))
            categorized[category].append(item)
        
        # Take 1-2 items from each category for diversity
        diversified = []
        max_per_category = 2
        
        for category in self.news_categories.keys():
            if category in categorized:
                # Sort by recency first (assuming 'date' is available or we use insertion order)
                # For now, rely on RAG ranking which should be relevance/recency aware
                category_items = categorized[category]
                
                # Filter out already mentioned news for this user
                if user_id:
                    category_items = [
                        item for item in category_items
                        if item.get('id') not in self.mentioned_news_cache.get(user_id, set())
                    ]
                
                # Take freshest items
                taken = 0
                for item in category_items:
                    if taken >= max_per_category:
                        break
                    diversified.append(item)
                    taken += 1
        
        # If we still need more items, fill with remaining freshest news
        if len(diversified) < self.max_news_per_query:
            all_items = news_items # Already sorted by retriever usually
            for item in all_items:
                if len(diversified) >= self.max_news_per_query:
                    break
                if item not in diversified:
                    diversified.append(item)
        
        # Limit to max_news_per_query
        return diversified[:self.max_news_per_query]
    
    def _categorize_news(self, content: str) -> str:
        """Categorize news content"""
        content_lower = content.lower()
        
        for category, keywords in self.news_categories.items():
            for keyword in keywords:
                if keyword in content_lower:
                    return category
        
        return 'general'
    
    def track_mentioned_news(self, news_ids: List[str], user_id: str):
        """Track which news has been mentioned to avoid repetition"""
        if not user_id or not news_ids:
            return
            
        self.mentioned_news_cache[user_id].update(news_ids)
        
        # Clean old cache (keep only last 100 mentioned items per user)
        if len(self.mentioned_news_cache[user_id]) > 100:
            self.mentioned_news_cache[user_id] = set(list(self.mentioned_news_cache[user_id])[-100:])
        
        self.save_mentioned_news()
            
    def get_user_excluded_topics(self, user_id: str) -> List[str]:
        """Placeholder for future feature to exclude topics"""
        return []



class RAGEnhancer:
    """Enhanced RAG configuration for news retrieval"""
    
    def __init__(self):
        self.news_query_params = {
            'similarity_top_k': 12,  # Retrieve more initially
            'mmr_threshold': 0.7,     # Use MMR for diversity
            'date_weight': 0.3,       # Weight recency
            'freshness_window_days': 3,
        }
        
        self.query_expansion_keywords = {
            'news': ['update', 'report', 'develop', 'situation', 'trend', 'analysis'],
            'tech': ['technology', 'innovation', 'development', 'release', 'launch'],
            'security': ['threat', 'attack', 'vulnerability', 'patch', 'exploit'],
        }
    
    def prepare_news_query(self, base_query: str, user_context: Dict = None) -> Dict:
        """Prepare enhanced query for news retrieval"""
        expanded_query = base_query
        
        # Add query expansion
        for category, keywords in self.query_expansion_keywords.items():
            if any(word in base_query.lower() for word in ['tech', 'technology', 'ai']):
                expanded_query += " " + " ".join(keywords[:2])
        
        # Add temporal context
        if 'recent' in base_query.lower() or 'latest' in base_query.lower():
            expanded_query += f" last {self.news_query_params['freshness_window_days']} days"
        
        # Prepare metadata filters
        filters = {
            'date': f">{datetime.now() - timedelta(days=7)}",
            'doc_type': 'news',
        }
        
        if user_context and 'exclude_topics' in user_context:
            filters['exclude_topics'] = user_context['exclude_topics']
        
        return {
            'query': expanded_query,
            'filters': filters,
            'params': self.news_query_params,
            'diversity': True,
        }
    
    def deduplicate_results(self, nodes: List[Any]) -> List[Any]:
        """Remove duplicate or highly similar news"""
        unique_contents = set()
        deduplicated = []
        
        for node in nodes:
            # Handle both LlamaIndex Nodes and dicts (if converted)
            text = getattr(node, 'text', None) or getattr(node, 'content', '') or str(node)
            
            content_hash = hashlib.md5(
                text[:500].encode()  # Hash first 500 chars for deduplication
            ).hexdigest()
            
            if content_hash not in unique_contents:
                unique_contents.add(content_hash)
                deduplicated.append(node)
        
        return deduplicated[:8]  # Return top 8 unique items
