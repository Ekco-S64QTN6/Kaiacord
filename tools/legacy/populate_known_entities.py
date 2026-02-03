#!/usr/bin/env python3
"""
Populate Kaia's known entities from existing knowledge base
"""

import json
import os
import yaml
from datetime import datetime
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def extract_entities_from_knowledge_base():
    """Extract known entities from all knowledge base files"""
    entities = {
        "users": set(),
        "organizations": set(),
        "projects": set(),
        "locations": set(),
        "technologies": set()
    }
    
    # Scan knowledge_base directory
    kb_root = "./knowledge_base"
    
    if not os.path.exists(kb_root):
        print(f"⚠️ Knowledge base directory not found: {kb_root}")
        return entities

    for root, dirs, files in os.walk(kb_root):
        for file in files:
            if file.endswith(('.md', '.json', '.txt', '.yaml', '.yml')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r') as f:
                        content = f.read()
                        entities = extract_entities_from_text(content, entities)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return entities

def extract_entities_from_text(text, entities_dict):
    """Extract entities from text content"""
    import re
    
    # Extract potential names (Title Case words)
    # Avoid common words by checking length and structure
    name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
    names = re.findall(name_pattern, text)
    
    common_words = {
        'The', 'A', 'An', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By',
        'And', 'Or', 'But', 'So', 'If', 'Then', 'Else', 'When', 'Where', 'Why',
        'How', 'Who', 'What', 'Is', 'Are', 'Was', 'Were', 'Be', 'Been', 'Being',
        'Have', 'Has', 'Had', 'Do', 'Does', 'Did', 'Can', 'Could', 'Should',
        'Would', 'May', 'Might', 'Must', 'Shall', 'Will', 'News', 'Latest',
        'Update', 'Technology', 'Politics', 'Security', 'Business', 'Science',
        'General', 'Kaia', 'Ai', 'Gpt', 'Llm', 'Api', 'Sql', 'Http', 'Json',
        'Yaml', 'Md', 'Txt', 'Html', 'Css', 'Js', 'Py', 'Sh', 'Bash', 'Linux',
        'Windows', 'Mac', 'Os', 'Android', 'Ios', 'App', 'Web', 'Site', 'Page'
    }

    for name in names:
        if name in common_words or len(name) < 3:
            continue
            
        # Simple heuristics to categorize
        if len(name.split()) == 1:  # Single word
            entities_dict["users"].add(name)
        elif any(org_word in name.lower() for org_word in ['inc', 'corp', 'llc', 'ltd', 'co', 'company', 'foundation', 'institute']):
            entities_dict["organizations"].add(name)
        elif any(tech_word in name.lower() for tech_word in ['gpt', 'ai', 'llm', 'api', 'sql', 'http']):
            entities_dict["technologies"].add(name)
        else:
            entities_dict["projects"].add(name)
    
    return entities_dict

def save_entity_database(entities):
    """Save entities to database"""
    output = {
        "timestamp": datetime.now().isoformat(),
        "entities": {k: list(v) for k, v in entities.items()}
    }
    
    os.makedirs("./memory", exist_ok=True)
    with open("./memory/entity_database.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Saved {sum(len(v) for v in entities.values())} entities to database")

if __name__ == "__main__":
    print("🔍 Scanning knowledge base for known entities...")
    entities = extract_entities_from_knowledge_base()
    save_entity_database(entities)
