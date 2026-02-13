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
        for subdir in ["Books", "news", "deep_dive_reports", "blogs", "forum_posts", "forum_posts/technical"]:
            folder = Path(self.kb_path) / subdir
            if folder.exists():
                # Extract potential entities from filenames (titles)
                for f in folder.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        # Clean up filename for entity check
                        clean_name = f.stem.replace("_", " ").replace("-", " ")
                        # Remove dates and version strings
                        clean_name = re.sub(r'\d{8}', '', clean_name)
                        # Remove thread prefixes
                        clean_name = clean_name.replace("thread", "").strip()
                        self.known_entities.add(clean_name.lower())

        # 3. Scan Identity Registry for linked forum/discord users
        registry_path = os.path.join(self.kb_path, "identity_registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r') as f:
                    reg_data = json.load(f)
                    # Extract forum names if they exist in mappings (not direct yet, but registry.json has some)
                    # For now, let's at least ensure common forum IDs/patterns are known
                    for discord_id in reg_data.get("mappings", {}):
                        self.known_entities.add(discord_id.lower())
                        # If we have forum UIDs, adding them directly isn't helpful as text
                        # but we can add common patterns like "Shovelquest" if we find them in directory names
            except Exception: pass

        log_success(f"Loaded {len(self.known_entities)} known entities into boundary.")
    
    def extract_entities(self, text: str) -> List[str]:
        """Extract potential person names from text"""
        # Simple pattern for names (capitalized words, 2+ chars)
        # Exclude common sentence starters if at beginning
        # Entity pattern: Capitalized word, potentially CamelCase or with numbers
        # Replaces [A-Z][a-z]+ with a more robust pattern
        pattern = r'\b([A-Z][A-Za-z0-9]*[a-z0-9][A-Za-z0-9]*)\b'
        matches = re.findall(pattern, text)
        
        # Filter out common words and system terms
        common_words = {
            'Kaia', 'AI', 'GPT', 'OpenAI', 'Google', 'Gemini', 'Anthropic', 'Claude',
            'Llama', 'Ollama', 'Mistral', 'Nvidia', 'Intel', 'Microsoft', 'Apple', 
            'The', 'And', 'But', 'Who', 'What', 'Where', 'When', 'Why', 'How',
            'Tell', 'Me', 'About', 'Is', 'Are', 'Was', 'Were', 'Do', 'Does',
            'Can', 'Could', 'Should', 'Would', 'News', 'Latest', 'Update',
            'technology', 'politics', 'security', 'business', 'science', 'general',
            'explain', 'describe', 'list', 'show', 'help', 'create', 'write',
            'make', 'draw', 'analyze', 'check', 'run', 'start', 'stop', 'open',
            'close', 'get', 'set', 'put', 'call', 'ask', 'say', 'see', 'look',
            'understood', 'indeed', 'correct', 'got', 'sure', 'fine', 'okay',
            'yes', 'no', 'true', 'false', 'good', 'bad', 'great', 'wait', 'hold', 
            'keep', 'stop', 'go', 'come', 'back', 'right', 'left', 'also', 'then', 
            'now', 'still', 'again', 'just', 'very', 'well', 'thanks', 'thank', 
            'please', 'sorry', 'excuse', 'maybe', 'probably', 'actually', 
            'basically', 'finally', 'lastly', 'first', 'second', 'third', 'here', 
            'there', 'every', 'some', 'any', 'all', 'both', 'neither', 'either', 
            'each', 'many', 'much', 'few', 'little', 'indeed',
            'research', 'project', 'technical', 'cheat', 'sheet', 'forum',
            'transcript', 'memory', 'internal', 'summary', 'notes', 'log',
            'reference', 'dossier', 'profile', 'analysis', 'report',
            'documentation', 'knowledge', 'base', 'system', 'library', 
            'review', 'audit', 'status', 'update', 'active', 'complete',
            'overview', 'purpose', 'objective', 'goal', 'conclusion', 'recommendation',
            'requirement', 'problem', 'fix', 'solution', 'maintenance', 'stabilization',
            'narrative', 'context', 'item', 'author', 'recipient', 'executive', 'lead',
            'integrity', 'identity', 'fragment', 'anchor',
            'planning', 'scrape', 'topic', 'wikipedia', 'quora', 'articles', 'instruction',
            'suggestion', 'verification', 'semantic', 'blindness', 'ratio', 'caveat',
            'predictable', 'rigidity', 'improving', 'exceeding', 'contrastive',
            # Log/Technical/Identity/Forum noise
            'User', 'Detected', 'Initializing', 'Populated', 'Success', 'Action', 'Found', 'Modified',
            'Processed', 'Processing', 'Indexed', 'Valid', 'Documents', 'Files',
            'Loading', 'Loaded', 'Checking', 'Starting', 'Started', 'Finished',
            'Completed', 'Failure', 'Error', 'Warning', 'Info', 'Debug', 'Running',
            'KaiaRAG', 'KaiaNews', 'KaiaForum', 'KaiaSocial', 'KaiaIntelligence',
            'Prompt', 'Per', 'Posts', 'Thread', 'Member', 'Quote', 'Originally', 'Post', 'Last', 'Page', 'Boundary'
        }
        
        # Case-insensitive set for filtering
        common_words_lower = {w.lower() for w in common_words}
        
        # Modern AI/Tech Filter Expansion (Gemini, Claude, GPT, etc.)
        modern_tech = {
            'Gemini', 'Google', 'DeepMind', 'Antigravity', 'OpenAI', 'GPT-4o', 'GPT-4', 'o1', 'Claude', 
            'Anthropic', 'Haiku', 'Sonnet', 'Opus', 'Llama', 'Meta', 'Mistral',
            'Flux', 'Midjourney', 'DALL-E', 'Stable', 'Diffusion', 'Github', 'Copilot',
            'Cursor', 'Vscode', 'Python', 'Javascript', 'React', 'Node', 'Docker',
            'P99', 'Norrath', 'EverQuest', 'Daybreak', 'Discord', 'VBulletin'
        }
        common_words_lower.update(w.lower() for w in modern_tech)

        # Core Lore keywords that are part of the bot's primary domain
        lore_keywords = {
            'Neuromancer', 'Hagakure', 'Sprawl', 'Wintermute', 'Tessier', 'Ashpool', 'Molly', 'Millions'
        }
        common_words_lower.update(w.lower() for w in lore_keywords)
        
        filtered_matches = []
        for m in matches:
            m_lower = m.lower()
            if m_lower in common_words_lower:
                continue
            if len(m) <= 2:
                continue
            # Basic check for pluralization of common words (e.g. "Files", "Boundaries")
            if m_lower.endswith('s'):
                if m_lower[:-1] in common_words_lower: # Simple 's'
                    continue
                if m_lower.endswith('ies') and m_lower[:-3] + 'y' in common_words_lower: # 'ies' to 'y'
                    continue
                if m_lower.endswith('es') and m_lower[:-2] in common_words_lower: # 'es'
                    continue
            filtered_matches.append(m)
            
        return filtered_matches
    
    def _is_lazy_match(self, entity_lower: str) -> bool:
        """Check filesystem for user logs if memory check fails (Dynamic Refresh)."""
        user_logs_dir = os.path.join(self.kb_path, "user_logs")
        if not os.path.exists(user_logs_dir):
            return False
            
        # Quick scan of matching starting folders
        # We don't want to re-scan EVERYTHING, just look for folders starting with entity
        try:
            for d_name in os.listdir(user_logs_dir):
                if d_name.lower().startswith(entity_lower + "_"):
                    # Found it! Add to memory cache to avoid repeat disk access
                    name = d_name.rsplit("_", 1)[0].replace("_", " ")
                    self.known_entities.add(name.lower())
                    return True
        except Exception:
            pass
        return False

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

    def check_known_entities(self, query: str, context: str, whitelist: Optional[Set[str]] = None) -> Dict:
        """Check if entities in query are known"""
        query_entities = self.extract_entities(query)
        whitelist_lower = {w.lower() for w in whitelist} if whitelist else set()
        
        # Check if entities appear in context
        known_in_context = []
        unknown_in_context = []
        
        context_lower = context.lower()
        
        for entity in query_entities:
            entity_lower = entity.lower()
            # Check if known globally, in whitelist, or in current context
            is_known = (
                entity_lower in self.known_entities or
                entity_lower in whitelist_lower or
                entity_lower in context_lower or
                f"{entity_lower}s" in context_lower or
                self._is_fuzzy_match(entity, context_lower) or
                self._is_lazy_match(entity_lower)  # Final disk-based fallback
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
