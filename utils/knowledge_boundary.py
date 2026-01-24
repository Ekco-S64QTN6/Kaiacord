import re
import os
import json
from typing import List, Dict, Set, Optional

class KnowledgeBoundary:
    """Prevents Kaia from making up information she doesn't know"""
    
    def __init__(self, knowledge_base_path="./knowledge_base", data_path="./data"):
        self.kb_path = knowledge_base_path
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

        # Also load directly from user profiles for freshness
        users_dir = os.path.join(self.kb_path, "user_profiles")
        if os.path.exists(users_dir):
            for file in os.listdir(users_dir):
                if file.endswith('.json'):
                    try:
                        with open(os.path.join(users_dir, file), 'r') as f:
                            data = json.load(f)
                            if 'name' in data:
                                self.known_entities.add(data['name'].lower())
                    except:
                        pass
    
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
            'Close', 'Get', 'Set', 'Put', 'Call', 'Ask', 'Say', 'See', 'Look'
        }
        return [m for m in matches if m not in common_words and len(m) > 2]
    
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
                f"{entity_lower}s" in context.lower()
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
