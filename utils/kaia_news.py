import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set
from collections import defaultdict
import re
import random
import hashlib
import os
import yaml
from pathlib import Path

# --- NEW FUNCTIONS FOR DIVERSITY ---
def get_diverse_news_topics():
    """Return diverse news categories beyond just CVEs"""
    return {
        "technology": {
            "weight": 0.25,
            "topics": [
                "AI breakthroughs", "Quantum computing", "Space exploration",
                "Consumer electronics", "Software updates", "Startup funding",
                "Gaming news", "Social media trends", "Chip manufacturing",
                "Renewable energy tech", "Biotech advances", "Robotics"
            ]
        },
        "politics": {
            "weight": 0.20,
            "topics": [
                "Elections", "Policy changes", "International relations",
                "Economic reforms", "Legislation", "Diplomatic meetings",
                "Political scandals", "Public protests", "Government spending",
                "Trade agreements", "Military developments", "Environmental policy"
            ]
        },
        "business": {
            "weight": 0.15,
            "topics": [
                "Stock market", "Mergers & acquisitions", "CEO changes",
                "Economic indicators", "Corporate earnings", "Market trends",
                "Cryptocurrency", "Real estate", "Consumer spending",
                "Supply chain issues", "Labor market", "Inflation data"
            ]
        },
        "security": {
            "weight": 0.15,
            "topics": [
                "Data breaches", "Ransomware attacks", "Vulnerability disclosures",
                "State-sponsored hacking", "Privacy regulations", "Cyber warfare",
                "Identity theft", "Phishing campaigns", "Supply chain attacks",
                "IoT security", "Cloud security", "Zero-day exploits"
            ]
        },
        "culture": {
            "weight": 0.10,
            "topics": [
                "Film & TV", "Music releases", "Celebrity news",
                "Art exhibitions", "Book releases", "Theater openings",
                "Gaming culture", "Internet memes", "Streaming services",
                "Fashion trends", "Food & dining", "Travel destinations"
            ]
        },
        "science": {
            "weight": 0.10,
            "topics": [
                "Medical breakthroughs", "Climate research", "Archaeology finds",
                "Physics discoveries", "Chemistry innovations", "Biology research",
                "Astronomy observations", "Environmental studies", "Psychology findings",
                "Mathematics proofs", "Engineering feats", "Oceanography discoveries"
            ]
        },
        "sports": {
            "weight": 0.05,
            "topics": [
                "Game results", "Player transfers", "Championship events",
                "Team standings", "Injury reports", "Coach changes",
                "Draft picks", "Record breaks", "Tournament schedules",
                "Olympic preparations", "Sports business", "Fan events"
            ]
        }
    }

def generate_news_summary(category=None):
    """Generate a more diverse news summary"""
    topics = get_diverse_news_topics()
    
    if not category or category not in topics:
        # Pick a random category weighted by importance
        weights = [topics[cat]["weight"] for cat in topics]
        categories = list(topics.keys())
        category = random.choices(categories, weights=weights, k=1)[0]
    
    # Pick a random topic from the category
    topic = random.choice(topics[category]["topics"])
    
    # Generate a more natural sounding summary
    templates = [
        f"On the {topic.lower()} front, {random.choice(['things are getting interesting', 'developments are moving fast', 'there have been some major shifts'])}. "
        f"{random.choice(['Sources indicate', 'Reports suggest', 'Industry insiders say'])} "
        f"{random.choice(['a significant announcement is expected soon', 'new regulations are being drafted', 'market forces are driving change'])}. "
        f"It's {random.choice(['definitely worth watching', 'something to keep an eye on', 'going to have ripple effects'])}.",
        
        f"Regarding {topic.lower()}, {random.choice(['the landscape is evolving', 'recent events have reshaped things', 'there\'s been notable progress'])}. "
        f"{random.choice(['Analysts are predicting', 'Experts are warning', 'Observers are noting'])} "
        f"{random.choice(['a paradigm shift in the making', 'unprecedented growth opportunities', 'potential regulatory challenges ahead'])}. "
        f"This could {random.choice(['change everything', 'open new doors', 'create interesting dynamics'])}.",
        
        f"Talk about {topic.lower()} - {random.choice(['it\'s been a busy week', 'developments are accelerating', 'the situation is fluid'])}. "
        f"{random.choice(['Key players are', 'Major organizations are', 'Governments are'])} "
        f"{random.choice(['rethinking their approach', 'doubling down on investments', 'forming new alliances'])}. "
        f"{random.choice(['Stay tuned', 'Watch this space', 'More to come'])}."
    ]
    
    return {
        "category": category,
        "topic": topic,
        "summary": random.choice(templates),
        "timestamp": datetime.now().isoformat()
    }

def get_news_categories():
    """Wrapper for compatibility"""
    return get_diverse_news_topics()

def get_news_summary(category=None):
    """Wrapper for compatibility"""
    return generate_news_summary(category)

# --- END NEW FUNCTIONS ---

class NewsManager:
    """Unified news manager for scanning, parsing, and retrieving news (Consolidated)"""
    
    def __init__(self, base_path="./knowledge_base/news"):
        self.base_path = Path(base_path)
        self.news_cache = defaultdict(list)
        self.last_refresh = None
        self.categories = {
            "technology": ["ai", "tech", "software", "hardware", "internet", "cyber", "digital", "chip", "tsmc", "nvidia"],
            "politics": ["election", "government", "policy", "senate", "congress", "president", "diplomatic", "legislation"],
            "business": ["market", "stock", "economy", "company", "corporate", "financial", "merger", "acquisition"],
            "security": ["hack", "breach", "cyber", "attack", "vulnerability", "cve", "ransomware", "exploit", "patch"],
            "science": ["research", "discovery", "study", "scientific", "breakthrough", "medical", "space", "astronomy"],
            "culture": ["movie", "tv", "celebrity", "music", "game", "art", "book", "fashion", "travel", "entertainment", "society", "trend"],
            "hacker": ["lapsus", "anonymous", "apt", "manifesto", "defcon", "blackhat", "ctf", "hacker", "cyberwarfare"]
        }
        self._ensure_base_path()
        self.refresh()

    def _ensure_base_path(self):
        """Ensure the news directory exists"""
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)
            (self.base_path / "daily").mkdir(exist_ok=True)

    def refresh(self):
        """Scan and parse all news files"""
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
                    print(f"⚠️ Error parsing {file_path}: {e}")
        
        self.last_refresh = datetime.now()

    def _parse_md_file(self, file_path: Path):
        """Parse markdown news file"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract date from filename or content
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path.name)
        date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        
        current_section = None
        current_items = []
        
        for line in content.split('\n'):
            if line.startswith('## '):
                if current_section:
                    self._add_to_cache(current_section, current_items, date, str(file_path))
                current_section = line[3:].strip()
                
                # Skip irrelevant sections
                if current_section.upper() in ['SOURCES', 'FAILURE_METRICS', 'QUOTES', 'EXECUTIVE_SUMMARY', 'HEADLINES']:
                    current_section = None
                    
                current_items = []
            elif line.startswith('- ') and current_section:
                current_items.append(line[2:].strip())
        
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
        if section_upper in ['SOURCES', 'FAILURE_METRICS', 'QUOTES', 'EXECUTIVE_SUMMARY', 'HEADLINES']:
            return None
            
        section_lower = section.lower()
        
        # Prioritize hacker if mentioned
        if 'hacker' in section_lower or 'cyberwarfare' in section_lower:
            return 'hacker'
            
        # Prioritize culture if explicitly mentioned in section name (and not hacker)
        if 'culture' in section_lower or 'entertainment' in section_lower:
            return 'culture'
            
        # Society can be general or culture depending on context, but let's map it to general if it has tech
        if 'society' in section_lower:
            if 'tech' in section_lower:
                return 'technology'
            return 'general'
            
        for cat, keywords in self.categories.items():
            if cat in section_lower or any(kw in section_lower for kw in keywords):
                return cat
        return 'general'

    def get_news(self, category: str = None, limit: int = 5) -> List[Dict]:
        """Retrieve news items, falling back to generated news if empty"""
        # Refresh if stale (5 mins)
        if not self.last_refresh or (datetime.now() - self.last_refresh).seconds > 300:
            self.refresh()
            
        category_lower = (category or 'general').lower()
        
        # Find best matching category
        matched_cat = None
        
        # Check if it matches a known category first
        for cat in self.categories.keys():
            if cat in category_lower or category_lower in cat:
                matched_cat = cat
                break
        
        if not matched_cat:
            matched_cat = 'general'
        
        items = self.news_cache.get(matched_cat, [])
        
        # NO FALLBACK to general if a specific category was requested
        if not items:
            return []

        # If still no items, generate some diverse news as fallback
        if not items:
            generated = generate_news_summary(category)
            return [{
                'text': generated['summary'],
                'date': datetime.now().strftime("%Y-%m-%d"),
                'source': 'Kaia Intelligence',
                'category': generated['category'],
                'topic': generated['topic']
            }]

        # Sort by date descending
        items.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Random sample if we have many
        if len(items) > limit * 2:
            return random.sample(items[:limit*2], limit)
        return items[:limit]

class NewsRetrievalEnhancer:
    """Advanced news retrieval system for Kaia"""
    
    def __init__(self, max_news_per_query: int = 8, days_of_freshness: int = 7):
        self.max_news_per_query = max_news_per_query
        self.days_of_freshness = days_of_freshness
        self.mentioned_news_cache = defaultdict(set)  # user_id -> set of news IDs
        self.news_categories = {
            'tech': ['tsmc', 'nvidia', 'azure', 'amd', 'intel', 'chip', 'hardware'],
            'security': ['cve', 'breach', 'zero-day', 'vulnerability', 'patch', 'exploit'],
            'ai': ['ai act', 'regulation', 'llm', 'model', 'training', 'inference'],
            'business': ['startup', 'funding', 'acquisition', 'merger', 'layoff'],
            'science': ['discovery', 'research', 'study', 'breakthrough'],
            'gaming': ['game', 'console', 'steam', 'playstation', 'xbox']
        }
    
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
            
        if user_id not in self.mentioned_news_cache:
            self.mentioned_news_cache[user_id] = set()
        
        self.mentioned_news_cache[user_id].update(news_ids)
        
        # Clean old cache (keep only last 50 mentioned items per user)
        if len(self.mentioned_news_cache[user_id]) > 50:
            # Convert to list to slice, then back to set
            # Note: Sets are unordered, so this is just random eviction, which is fine for now
            # Ideally we'd use an OrderedDict or similar if order mattered strictly
            self.mentioned_news_cache[user_id] = set(list(self.mentioned_news_cache[user_id])[-50:])
            
    def get_user_excluded_topics(self, user_id: str) -> List[str]:
        """Placeholder for future feature to exclude topics"""
        return []

class ResponseEnhancer:
    """Enhance Kaia's response quality and diversity"""
    
    def __init__(self):
        self.news_intros = [
            "Here's what's caught my attention recently:",
            "The chatter in the data streams suggests:",
            "From what I've been parsing in the feeds:",
            "A few things have been making waves:",
            "The network's buzzing about:",
            "Here's the current situation as I see it:"
        ]
        
        self.identity_intros = {
                'casual': [""],
                'direct': [""]
            }
        
        self.endings = []  # EMPTY - NO BOILERPLATE QUESTIONS  # EMPTY - NO BOILERPLATE QUESTIONS  # REMOVED: No more boilerplate questions
    
    def enhance_news_response(self, news_items: List[Dict]) -> str:
        """Generate better formatted news responses"""
        if not news_items:
            return "Nothing new on the wires. Everything's quiet. Too quiet."
        
        intro = random.choice(self.news_intros)
        response_parts = [intro, ""]
        
        for i, item in enumerate(news_items[:6]):  # Limit to 6 news items
            # Extract key points
            content = item.get('content', '')
            
            # Create concise summary
            summary = self._summarize_news(content)
            
            # Format each news item
            response_parts.append(f"• **{summary}**")
            
            # Add details for first 3 items
            if i < 3 and len(content) > 100:
                details = self._extract_details(content)
                if details:
                    response_parts.append(f"  {details}")
            
            response_parts.append("")
        
        # Add context or analysis
        if len(news_items) > 3:
            response_parts.append(f"That's just the highlights from {len(news_items)} separate threads I'm tracking.")
        
        # REMOVED: No more adding boilerplate endings
        
        return "\n".join(response_parts)
    
    def enhance_identity_response(self, base_response: str, query_type: str = 'casual') -> str:
        """Improve identity responses"""
        # Remove repetitive patterns using regex
        # Matches "Look," "Listen," "Honestly," "Well," at start of string, case insensitive
        base_response = re.sub(r'^(look|listen|honestly|well|so|right)[,\s]+', '', base_response.strip(), flags=re.IGNORECASE)
        
        # Replace with varied intro
        intro = random.choice(self.identity_intros[query_type])
        
        # If the response starts with "i'm" or "i am", we can just prepend the intro
        # Otherwise, we might need to be careful. 
        # But usually "Look, I'm Kaia" -> "I'm Kaia" -> "Honestly, I'm Kaia" works.
        base_response = intro + base_response
        
        # Remove formulaic endings
        endings_to_remove = ["what about it?", "what is it?", "now, what is it?"]
        for ending in endings_to_remove:
            if base_response.strip().lower().endswith(ending):
                base_response = base_response.strip()[:-len(ending)].rstrip()
                if not base_response.endswith('.'):
                    base_response += "."
                break
        
        # Ensure response ends with engagement
        # REMOVED: No more adding boilerplate endings
        
        return base_response
    
    def _summarize_news(self, content: str) -> str:
        """Extract key sentence from news"""
        sentences = content.split('.')
        if len(sentences) > 1:
            return sentences[0].strip() + "."
        return content[:100].strip() + "..."
    
    def _extract_details(self, content: str) -> str:
        """Extract important details"""
        # Look for key details: dates, numbers, impacts
        patterns = [
            r'(\d+ million records?)',
            r'CVE-\d{4}-\d+',
            r'(\d+ days?) delay',
            r'impacting (\d+%?)',
            r'\$\d+ billion',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content.lower())
            if match:
                return match.group(0).capitalize()
        
        return ""

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
