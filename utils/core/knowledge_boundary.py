import re
import os
import json
from typing import List, Dict, Set, Optional, Union
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action, log_debug, log_warning, log_error

class KnowledgeBoundary:
    """Prevents Kaia from making up information she doesn't know"""
    
    def __init__(self, knowledge_base_dir="./knowledge_base", data_path="./memory", config_path="./config"):
        self.kb_path = knowledge_base_dir
        self.data_path = data_path
        self.config_path = config_path
        self.known_entities = set()
        self.common_words_lower = set()
        self.acronyms = set()
        self.fuzzy_max_context_words = 500  # Default fallback
        
        # Precompiled regex patterns for performance
        self._title_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')
        self._acronym_pattern = re.compile(r'\b([A-Z]{2,})\b')
        self._article_prefix = re.compile(r'^(The|A|An)\s+', re.I)
        self._date_pattern = re.compile(r'\d{8}')
        
        self.load_common_entities()
        self.load_known_entities()
        
    def load_common_entities(self):
        """Load common words and acronyms from config file"""
        cf_path = os.path.join(self.config_path, "common_entities.json")
        if os.path.exists(cf_path):
            try:
                with open(cf_path, 'r') as f:
                    data = json.load(f)
                    self.common_words_lower = {w.lower() for w in data.get("common_words", [])}
                    self.acronyms = set(data.get("acronyms", []))
                    self.fuzzy_max_context_words = data.get("fuzzy_max_context_words", 500)
                log_debug(f"Loaded {len(self.common_words_lower)} common terms and {len(self.acronyms)} acronyms (fuzzy threshold: {self.fuzzy_max_context_words}).")
            except Exception as e:
                log_error(f"Error loading common_entities.json: {e}")
        else:
            log_warning("common_entities.json not found. Using empty filter set.")

    def load_known_entities(self):
        """Load known entities from database and knowledge base"""
        # Load from generated database
        db_path = os.path.join(self.data_path, "entity_database.json")
        if os.path.exists(db_path):
            try:
                with open(db_path, 'r') as f:
                    data = json.load(f)
                    if 'entities' in data:
                        for category in data['entities'].values():
                            self.known_entities.update(e.lower() for e in category)
            except Exception as e:
                log_error(f"Error loading entity database: {e}")

        # 1. Scan User Logs (High Priority) - Pre-load usernames to avoid disk scans
        user_logs_dir = os.path.join(self.kb_path, "user_logs")
        if os.path.exists(user_logs_dir):
            try:
                for d_name in os.listdir(user_logs_dir):
                    d = os.path.join(user_logs_dir, d_name)
                    if os.path.isdir(d) and "_" in d_name:
                        name = d_name.rsplit("_", 1)[0].replace("_", " ")
                        self.known_entities.add(name.lower())
            except Exception as e:
                log_error(f"Error scanning user logs: {e}")

        # 2. Scan Knowledge Subdirectories (Books, News, Technical, etc.)
        from pathlib import Path
        subdirs = [
            "Books", "news", "deep_dive_reports", "blogs", "forum_posts", 
            "forum_posts/technical", "technical", "infrastructure", "security_research"
        ]
        for subdir in subdirs:
            folder = Path(self.kb_path) / subdir
            if folder.exists():
                for f in folder.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        clean_name = f.stem.replace("_", " ").replace("-", " ")
                        clean_name = self._date_pattern.sub('', clean_name)
                        clean_name = clean_name.replace("thread", "").strip()
                        self.known_entities.add(clean_name.lower())

        # 3. Scan Identity Registry
        registry_path = os.path.join(self.kb_path, "identity_registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r') as f:
                    reg_data = json.load(f)
                    for discord_id in reg_data.get("mappings", {}):
                        self.known_entities.add(discord_id.lower())
            except Exception: pass

        log_success(f"Loaded {len(self.known_entities)} known entities into boundary.")

    def register_usernames(self, names):
        """Register Discord guild member names as known entities at runtime."""
        for name in names:
            if name:
                self.known_entities.add(name.lower())
    
    def extract_entities(self, text: str) -> list:
        """Extract unknown entities from the text."""
        # 1. Broadly find all capitalized sequences (Title Case words)
        # Matches single words or multi-word phrases: "John" or "John Doe"
        title_matches = self._title_pattern.findall(text)
        
        # 2. Add Acronym support (NASA, GPU)
        acronym_matches = self._acronym_pattern.findall(text)
        
        all_matches = title_matches + acronym_matches
        
        filtered_matches = []
        for m in all_matches:
            original_m = m
            m = self._article_prefix.sub('', m)
            m_lower = m.lower()
            
            if m_lower in self.common_words_lower:
                continue
            
            if len(m) <= 2: # Very short acronyms or words
                continue
            
            # Skip single words that look like mashed-together usernames (e.g. Orginalcontentguy)
            if ' ' not in m and len(m) > 15:
                continue

            # Multi-word phrases are high signal
            if ' ' in original_m:
                if m_lower in self.common_words_lower:
                    continue
                
                # NEW: Check if all components are individually common or known
                # This prevents "Hi Kaia" from being flagged if "Hi" and "Kaia" are individually known.
                words = [w.lower() for w in m.split()]
                if all(w in self.common_words_lower or w in self.known_entities for w in words):
                    continue
                    
                filtered_matches.append(m)
                continue

            # Sentence Start Nuance
            escaped_m = re.escape(m)
            pattern = re.compile(r'(?<!^)(?<![.!?]\s)' + escaped_m + r'\b')
            is_non_start = pattern.search(text)
            
            if not is_non_start:
                if m_lower in self.known_entities:
                    filtered_matches.append(m)
                continue

            # Pluralization check
            if m_lower.endswith('s'):
                singular = None
                if m_lower.endswith('ies'): singular = m_lower[:-3] + 'y'
                elif m_lower.endswith('es'): singular = m_lower[:-2]
                else: singular = m_lower[:-1]
                
                if singular in self.common_words_lower:
                    continue

            filtered_matches.append(m)
            
        return list(set(filtered_matches))

    def check_known_entities(self, query: str, context: Union[str, List[str]], whitelist: Optional[Set[str]] = None) -> Dict:
        """Verify if entities in query are known to the system/context."""
        query_entities = self.extract_entities(query)
        whitelist_lower = {w.lower() for w in whitelist} if whitelist else set()
        
        known_in_context = []
        unknown_in_context = []
        
        # Optimized tokenization without massive join
        context_tokens = set()
        if isinstance(context, list):
            for part in context:
                context_tokens.update(part.lower().split())
            # For fuzzy match, we still need a string but we only build it if needed/small
            full_context_lower = " ".join(context).lower() if context else ""
        else:
            full_context_lower = context.lower()
            context_tokens = set(full_context_lower.split())
        
        for entity in query_entities:
            entity_lower = entity.lower()
            is_known = (
                entity_lower in self.known_entities or
                entity_lower in whitelist_lower or
                entity_lower in context_tokens or
                f"{entity_lower}s" in context_tokens or
                self._is_fuzzy_match(entity, full_context_lower)
            )
            
            if is_known:
                known_in_context.append(entity)
            else:
                unknown_in_context.append(entity)
        
        if unknown_in_context:
            log_msg = f"Knowledge Boundary: Detected potential unknown Lore entities: {unknown_in_context}"
            if any(len(e.split()) > 1 for e in unknown_in_context) or len(unknown_in_context) > 2:
                log_info(log_msg)
            else:
                log_debug(log_msg)

        return {
            "query_entities": query_entities,
            "known_in_context": known_in_context,
            "unknown_in_context": unknown_in_context,
            "all_known": len(unknown_in_context) == 0,
            "suggestions": self._get_entity_suggestions(unknown_in_context)
        }

    def _get_entity_suggestions(self, unknown_entities: List[str]) -> Dict[str, List[str]]:
        """Find potential known entities that contain the unknown term as a substring."""
        suggestions = {}
        for entity in unknown_entities:
            entity_l = entity.lower()
            # Find all known entities that contain this unknown term
            matches = [e for e in self.known_entities if entity_l in e and entity_l != e]
            if matches:
                # Sort by shortest match first (most specific to least specific)
                matches.sort(key=len)
                suggestions[entity] = matches[:3] # Top 3 suggestions
        return suggestions

    def _is_lazy_match(self, entity_lower: str) -> bool:
        """Deprecated: Lazy matching is now handled by pre-loading in load_known_entities."""
        return entity_lower in self.known_entities

    def _is_fuzzy_match(self, entity: str, context: str) -> bool:
        """Check for fuzzy matches (typos) in context."""
        if len(entity) < 4: return False
        entity_l = entity.lower()
        context_l = context.lower()
        
        if entity_l in context_l or context_l in entity_l:
            return True
            
        # PERFORMANCE GUARD: Skip if context is too large
        # Efficient words check using count
        if context_l.count(" ") > self.fuzzy_max_context_words:
            log_debug(f"Fuzzy match skipped: Context too large ({context_l.count(' ')} words).")
            return False
            
        words = context_l.split()
            
        target_words = [w.strip('.,!?:;"') for w in words if len(w) >= 4]
        for word in target_words:
            if abs(len(word) - len(entity_l)) > 1:
                continue
            if self._levenshtein_distance(entity_l, word) <= 1:
                return True
        return False

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if not s2:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]
    
    def generate_boundary_response(self, unknown_entities: List[str], query: str) -> str:
        """Generate a response that admits lack of knowledge"""
        if not unknown_entities:
            return None
        
        entity_str = ", ".join(unknown_entities)
        
        responses = [
            f"I don't have any information about {entity_str} in my knowledge base. They might be from a story or context I'm not familiar with.",
            f"{entity_str}... those names don't ring a bell. They're not in any of my records.",
            f"I can't find any references to {entity_str} in what I know. Are they characters from something specific?",
            f"Those names - {entity_str} - aren't in my knowledge base. I don't want to make up stories about people I don't actually know.",
            f"I don't have any context on {entity_str}. They might be from fiction, or personal knowledge I don't have access to."
        ]
        
        import random
        return random.choice(responses)
