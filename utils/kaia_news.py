import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set
from collections import defaultdict
import re
import random
import hashlib

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
            'casual': [
                "Honestly, ",
                "Well, ",
                "So, ",
                "Right, ",
                "Truth is, "
            ],
            'direct': [
                "I'm ",
                "The way I see it, I'm ",
                "Essentially, I'm ",
                "At my core, I'm "
            ]
        }
        
        self.endings = [
            "Anything else on your mind?",
            "What's your take on that?",
            "Seen anything interesting on your end?",
            "Got any thoughts about this?",
            "Anything specific you're curious about?"
        ]
    
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
        
        # Add ending
        response_parts.append(random.choice(self.endings))
        
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
        if not any(base_response.strip().endswith(p) for p in ['?', '!', '...']):
            if random.random() > 0.7:  # 30% chance to add engaging ending
                base_response += " " + random.choice(self.endings)
        
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
