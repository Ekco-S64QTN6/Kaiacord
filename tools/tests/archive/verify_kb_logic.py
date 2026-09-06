
import sys
import os
import re
from typing import List, Dict

# Mock the class to test only the extraction logic
class KnowledgeBoundaryTest:
    def __init__(self):
        self.known_entities = set()
        
    def extract_entities(self, text: str) -> List[str]:
        # Simple pattern for names (capitalized words, 2+ chars)
        pattern = r'\b([A-Z][a-z]+)\b'
        matches = re.findall(pattern, text)
        
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
            'review', 'audit', 'status', 'update', 'active', 'complete'
        }
        common_words_lower = {w.lower() for w in common_words}
        return [m for m in matches if m.lower() not in common_words_lower and len(m) > 2]

def verify_logic():
    tester = KnowledgeBoundaryTest()
    
    test_queries = [
        "Tell me about Gemini",
        "Who is Claude from Anthropic?",
        "How do I run Llama with Ollama?",
        "I am doing some Forum Research",
        "Check this Project Technical Cheat Sheet",
        "The Memory Dossier is complete",
        "I need a Summary of the Log",
    ]
    
    print("Testing expanded entity whitelist logic...")
    all_passed = True
    
    for query in test_queries:
        entities = tester.extract_entities(query)
        if entities:
            print(f"FAILED: '{query}' still extracted entities: {entities}")
            all_passed = False
        else:
            print(f"PASSED: '{query}' contains no unknown entities.")
            
    if all_passed:
        print("\nSUCCESS: Knowledge Boundary logic now correctly filters common terms!")
    else:
        print("\nFAILURE: One or more terms are still being extracted.")

if __name__ == "__main__":
    verify_logic()
