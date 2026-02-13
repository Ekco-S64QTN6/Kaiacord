import re
import os
import json
from typing import List, Dict, Set, Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action

class KnowledgeBoundary:
    """Prevents Kaia from making up information she doesn't know"""
    
    def __init__(self, knowledge_base_dir="./knowledge_base", data_path="./memory"):
        self.kb_path = knowledge_base_dir
        self.data_path = data_path
        self.known_entities = set()
        self.load_known_entities()
        
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
                print(f"Error loading entity database: {e}")

        # 1. Scan User Logs (High Priority)
        user_logs_dir = os.path.join(self.kb_path, "user_logs")
        if os.path.exists(user_logs_dir):
            for d_name in os.listdir(user_logs_dir):
                d = os.path.join(user_logs_dir, d_name)
                if os.path.isdir(d) and "_" in d_name:
                    name = d_name.rsplit("_", 1)[0].replace("_", " ")
                    self.known_entities.add(name.lower())

        # 2. Scan Knowledge Subdirectories (Books, News, etc.)
        from pathlib import Path
        import re
        for subdir in ["Books", "news", "deep_dive_reports", "blogs"]:
            folder = Path(self.kb_path) / subdir
            if folder.exists():
                # Extract potential entities from filenames (titles)
                for f in folder.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        # Clean up filename for entity check
                        clean_name = f.stem.replace("_", " ").replace("-", " ")
                        # Remove dates and version strings
                        clean_name = re.sub(r'\d{8}', '', clean_name)
                        self.known_entities.add(clean_name.strip().lower())

        log_success(f"Loaded {len(self.known_entities)} known entities into boundary.")
    
    def extract_entities(self, text: str) -> List[str]:
        """Extract potential person names from text"""
        # Simple pattern for names (capitalized words, 2+ chars)
        # Exclude common sentence starters if at beginning
        pattern = r'\b([A-Z][a-z]+)\b'
        matches = re.findall(pattern, text)
        
        # Filter out common words and system terms
        common_words = {
            'Kaia', 'AI', 'GPT', 'OpenAI', 'Google', 'Microsoft', 'Apple', 
            'The', 'And', 'But', 'Who', 'What', 'Where', 'When', 'Why', 'How',
            'Tell', 'Me', 'About', 'Is', 'Are', 'Was', 'Were', 'Do', 'Does',
            'Can', 'Could', 'Should', 'Would', 'News', 'Latest', 'Update',
            'Technology', 'Politics', 'Security', 'Business', 'Science', 'General',
            'Explain', 'Describe', 'List', 'Show', 'Help', 'Create', 'Write',
            'Make', 'Draw', 'Analyze', 'Check', 'Run', 'Start', 'Stop', 'Open',
            'Close', 'Get', 'Set', 'Put', 'Call', 'Ask', 'Say', 'See', 'Look',
            'Understood', 'Yes', 'No', 'True', 'False', 'Good', 'Bad', 'Great',
            'Wait', 'Hold', 'Keep', 'Stop', 'Go', 'Come', 'Back', 'Right', 'Left',
            'Also', 'Then', 'Now', 'Still', 'Again', 'Just', 'Very', 'Well',
            'Thanks', 'Thank', 'Please', 'Sorry', 'Excuse', 'Maybe', 'Probably',
            'Actually', 'Basically', 'Basically', 'Finally', 'Lastly', 'First',
            'Second', 'Third', 'Here', 'There', 'Every', 'Some', 'Any', 'All',
            'Both', 'Neither', 'Either', 'Each', 'Many', 'Much', 'Few', 'Little',
            'Understood', 'Indeed', 'Correct', 'Got', 'Sure', 'Fine', 'Okay'
        }
        
        # Case-insensitive set for filtering
        common_words_lower = {w.lower() for w in common_words}
        
        return [m for m in matches if m.lower() not in common_words_lower and len(m) > 2]
    
    def _is_fuzzy_match(self, entity: str, context: str) -> bool:
        """Check for fuzzy matches (typos) in context."""
        if len(entity) < 4: return False
        entity_l = entity.lower()
        context_l = context.lower()
        
        # 1. Check if the entity is a substring or vice versa (common for truncated names)
        if entity_l in context_l or context_l in entity_l:
            return True
            
        # 2. Check for single-character typos (Levenshtein distance 1)
        # We split context into words to avoid expensive full-string distance calc
        words = re.findall(r'\b[a-z]{4,}\b', context_l)
        for word in words:
            # Quick length filter
            if abs(len(word) - len(entity_l)) > 1:
                continue
            
            # Simple Levenshtein distance 1 check
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

    def check_known_entities(self, query: str, context: str) -> Dict:
        """Check if entities in query are known"""
        query_entities = self.extract_entities(query)
        
        # Check if entities appear in context
        known_in_context = []
        unknown_in_context = []
        
        for entity in query_entities:
            entity_lower = entity.lower()
            # Check if known globally or in current context
            is_known = (
                entity_lower in self.known_entities or
                entity_lower in context.lower() or
                f"{entity_lower}s" in context.lower() or
                self._is_fuzzy_match(entity, context)
            )
            
            if is_known:
                known_in_context.append(entity)
            else:
                unknown_in_context.append(entity)
        
        return {
            "query_entities": query_entities,
            "known_in_context": known_in_context,
            "unknown_in_context": unknown_in_context,
            "all_known": len(unknown_in_context) == 0
        }
    
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
