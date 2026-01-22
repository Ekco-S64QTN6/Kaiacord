"""
User Profile Generator for Kaia
Enhanced version with intelligent pattern recognition and relationship mapping
"""

import os
import glob
import asyncio
import json
import re
from datetime import datetime
from collections import Counter
from typing import Dict, List, Tuple, Optional
import ollama

# Configuration
LOG_DIR = "knowledge_base/user_logs"
MODEL = "gemma3:12b"  # Using the same model as Kaia for consistency

class UserProfileGenerator:
    def __init__(self, user_folder: str):
        self.user_folder = user_folder
        self.user_name = os.path.basename(user_folder).rsplit("_", 1)[0].replace("_", " ")
        self.log_files = sorted(glob.glob(os.path.join(user_folder, "interactions_*.txt")))
        self.all_content = ""
        self.messages = []
        self.analysis = {}
        
    async def load_and_preprocess(self):
        """Load and preprocess all log files for the user"""
        print(f"Loading logs for {self.user_name}...")
        
        for log_file in self.log_files:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                self.all_content += content + "\n"
                
                # Parse messages while preserving context
                lines = content.split("\n")
                current_speaker = None
                current_message = []
                timestamp = None
                
                for line in lines:
                    # Extract timestamp if present
                    if line.startswith("--- "):
                        if current_speaker and current_message:
                            self.messages.append({
                                "speaker": current_speaker,
                                "content": "\n".join(current_message).strip(),
                                "timestamp": timestamp
                            })
                        current_message = []
                        current_speaker = None
                        
                        # Try to parse timestamp: --- 20260120_131740 ---
                        try:
                            ts_str = line.strip("- ").strip()
                            timestamp = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                        except:
                            timestamp = None
                    elif "User (" in line and "):" in line:
                        current_speaker = "user"
                        # Extract message after User (Name):
                        msg_part = line.split("):", 1)[1].strip()
                        current_message.append(msg_part)
                        # Try to extract timestamp
                        if line.startswith("[") and "]" in line:
                            timestamp_part = line[1:].split("]", 1)[0]
                            try:
                                timestamp = datetime.strptime(timestamp_part, "%Y-%m-%d %H:%M:%S")
                            except:
                                timestamp = None
                    elif "Kaia:" in line or "KAIA:" in line:
                        current_speaker = "kaia"
                        # Extract message after Kaia:
                        prefix = "Kaia:" if "Kaia:" in line else "KAIA:"
                        msg_part = line.split(prefix, 1)[1].strip()
                        current_message.append(msg_part)
                    elif current_speaker and line.strip():
                        current_message.append(line.strip())
                
                # Don't forget the last message
                if current_speaker and current_message:
                    self.messages.append({
                        "speaker": current_speaker,
                        "content": "\n".join(current_message).strip(),
                        "timestamp": timestamp
                    })
    
    def extract_basic_stats(self):
        """Extract basic statistics from conversation history"""
        if not self.messages:
            return {}
        
        user_msgs = [m for m in self.messages if m["speaker"] == "user"]
        
        # Message frequency pattern
        msg_dates = []
        for msg in user_msgs:
            if msg["timestamp"]:
                msg_dates.append(msg["timestamp"].date())
        
        # Calculate interaction frequency
        freq_pattern = "irregular"
        if msg_dates:
            date_counts = Counter(msg_dates)
            avg_per_day = len(user_msgs) / len(set(msg_dates)) if msg_dates else 0
            if avg_per_day > 3:
                freq_pattern = "frequent"
            elif avg_per_day > 0.5:
                freq_pattern = "regular"
            else:
                freq_pattern = "sporadic"
        
        # Response time analysis (simple)
        avg_msg_length = sum(len(m["content"]) for m in user_msgs) / len(user_msgs) if user_msgs else 0
        
        return {
            "total_interactions": len(user_msgs),
            "message_frequency": freq_pattern,
            "avg_message_length": round(avg_msg_length),
            "first_seen": min([m["timestamp"] for m in self.messages if m["timestamp"]], default=None),
            "last_seen": max([m["timestamp"] for m in self.messages if m["timestamp"]], default=None),
        }
    
    def extract_topic_patterns(self):
        """Extract recurring topics and interests"""
        if not self.messages:
            return {}
        
        user_content = " ".join([m["content"].lower() for m in self.messages if m["speaker"] == "user"])
        
        # Topic keywords (expandable)
        topic_keywords = {
            "programming": ["python", "javascript", "rust", "go", "java", "code", "programming", "algorithm", "api", "library", "framework"],
            "systems": ["linux", "server", "docker", "kubernetes", "devops", "infrastructure", "deployment", "cloud", "aws", "azure"],
            "security": ["security", "hack", "vulnerability", "encryption", "privacy", "pentest", "malware", "firewall"],
            "hardware": ["pc", "gpu", "cpu", "ram", "motherboard", "raspberry", "arduino", "electronics", "soldering"],
            "philosophy": ["philosophy", "consciousness", "meaning", "existential", "ethics", "morality", "reality"],
            "creative": ["art", "music", "writing", "design", "creative", "drawing", "photography", "film"],
            "gaming": ["game", "gaming", "steam", "playstation", "xbox", "nintendo", "rpg", "fps"],
            "personal": ["family", "friend", "relationship", "work", "job", "career", "health", "mental"]
        }
        
        topic_counts = {}
        for topic, keywords in topic_keywords.items():
            count = sum(1 for keyword in keywords if keyword in user_content)
            if count > 0:
                topic_counts[topic] = count
        
        # Sort by frequency
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Extract specific project mentions
        project_pattern = r'(?:project|working on|building|developing)[\s\w]+?["\']?([A-Z][\w\s]+?)(?:["\']|\.|$)'
        projects = re.findall(project_pattern, user_content, re.IGNORECASE)
        
        # Extract potential usernames/handles
        handle_pattern = r'(?:github|twitter|discord|handle|username)[\s:]+[@]?(\w+)'
        handles = re.findall(handle_pattern, user_content, re.IGNORECASE)
        
        return {
            "primary_interests": [topic for topic, count in sorted_topics[:5]],
            "mentioned_projects": list(set(projects))[:10],
            "potential_handles": list(set(handles))[:5]
        }
    
    def analyze_conversation_style(self):
        """Analyze the user's conversational style"""
        if not self.messages:
            return {}
        
        user_messages = [m["content"] for m in self.messages if m["speaker"] == "user"]
        
        # Style indicators
        style_data = {
            "formality": 0,
            "technical_depth": 0,
            "humor_frequency": 0,
            "emotional_tone": 0,
            "question_ratio": 0
        }
        
        # Analyze each message
        for msg in user_messages:
            msg_lower = msg.lower()
            
            # Formality (capitalization, punctuation)
            if msg and msg[0].isupper():
                style_data["formality"] += 1
            if msg.endswith(('.', '!', '?')):
                style_data["formality"] += 0.5
            
            # Technical depth
            tech_terms = ["error", "bug", "debug", "compile", "server", "database", "api", "function", "class"]
            style_data["technical_depth"] += sum(1 for term in tech_terms if term in msg_lower)
            
            # Humor
            humor_indicators = ["lol", "haha", "lmao", "😂", "🤣", "funny", "joke"]
            style_data["humor_frequency"] += sum(1 for indicator in humor_indicators if indicator in msg_lower)
            
            # Emotional tone
            positive_words = ["thanks", "thank", "awesome", "great", "love", "happy", "excited"]
            negative_words = ["fuck", "shit", "damn", "hate", "angry", "frustrated", "annoyed"]
            style_data["emotional_tone"] += sum(1 for word in positive_words if word in msg_lower)
            style_data["emotional_tone"] -= sum(1 for word in negative_words if word in msg_lower)
            
            # Question ratio
            if msg.strip().endswith('?'):
                style_data["question_ratio"] += 1
        
        # Normalize
        total_msgs = len(user_messages)
        if total_msgs > 0:
            for key in style_data:
                style_data[key] = round(style_data[key] / total_msgs, 2)
        
        # Determine style labels
        style_labels = []
        
        if style_data["formality"] > 0.7:
            style_labels.append("formal")
        elif style_data["formality"] < 0.3:
            style_labels.append("casual")
        
        if style_data["technical_depth"] > 0.5:
            style_labels.append("technical")
        
        if style_data["humor_frequency"] > 0.3:
            style_labels.append("humorous")
        
        if style_data["emotional_tone"] > 0.3:
            style_labels.append("positive/enthusiastic")
        elif style_data["emotional_tone"] < -0.3:
            style_labels.append("direct/blunt")
        
        if style_data["question_ratio"] > 0.5:
            style_labels.append("inquisitive")
        
        return {
            "style_labels": style_labels,
            "metrics": style_data,
            "signature_phrases": self.extract_signature_phrases(user_messages)
        }
    
    def extract_signature_phrases(self, messages: List[str]) -> List[str]:
        """Extract phrases the user frequently uses"""
        if not messages:
            return []
        
        # Simple n-gram extraction (bigrams and trigrams)
        all_words = []
        for msg in messages:
            words = msg.lower().split()
            all_words.extend(words)
        
        # Count bigrams
        bigrams = Counter()
        for i in range(len(all_words) - 1):
            bigram = f"{all_words[i]} {all_words[i+1]}"
            bigrams[bigram] += 1
        
        # Get most common phrases (excluding very common ones)
        common_bigrams = [(phrase, count) for phrase, count in bigrams.items() 
                         if count > 2 and len(phrase.split()) == 2]
        
        # Sort and return
        common_bigrams.sort(key=lambda x: x[1], reverse=True)
        return [phrase for phrase, count in common_bigrams[:10]]
    
    def analyze_relationship_with_kaia(self):
        """Analyze the evolving relationship with Kaia"""
        if len(self.messages) < 10:
            return {"stage": "new", "trust_level": "low", "familiarity": "developing"}
        
        # Split messages into thirds to see evolution
        third = len(self.messages) // 3
        early_msgs = self.messages[:third]
        late_msgs = self.messages[2*third:] if third > 0 else []
        
        # Analyze trust indicators
        trust_indicators = [
            "personal story", "vulnerability", "asking for advice",
            "sharing failure", "expressing doubt", "thank you"
        ]
        
        early_trust = 0
        late_trust = 0
        
        for msg in early_msgs:
            if msg["speaker"] == "user":
                content = msg["content"].lower()
                early_trust += sum(1 for indicator in trust_indicators if indicator in content)
        
        for msg in late_msgs:
            if msg["speaker"] == "user":
                content = msg["content"].lower()
                late_trust += sum(1 for indicator in trust_indicators if indicator in content)
        
        # Determine relationship stage
        if len(self.messages) > 50 and late_trust > early_trust * 2:
            stage = "established"
            trust_level = "high"
        elif len(self.messages) > 20:
            stage = "developing"
            trust_level = "medium"
        else:
            stage = "early"
            trust_level = "low"
        
        # Check for personal connections
        personal_topics = ["how are you", "how's your", "you doing", "you okay"]
        personal_count = 0
        for msg in self.messages:
            if msg["speaker"] == "user":
                content = msg["content"].lower()
                if any(topic in content for topic in personal_topics):
                    personal_count += 1
        
        familiarity = "personal" if personal_count > 3 else "professional"
        
        return {
            "stage": stage,
            "trust_level": trust_level,
            "familiarity": familiarity,
            "trust_growth": late_trust - early_trust,
            "asks_personal_questions": personal_count > 0
        }
    
    def generate_llm_profile(self, stats: Dict, topics: Dict, style: Dict, relationship: Dict) -> str:
        """Generate the final profile using LLM with structured data"""
        
        # Prepare structured data for the LLM
        structured_data = {
            "user_name": self.user_name,
            "interaction_stats": stats,
            "interests_topics": topics,
            "conversation_style": style,
            "relationship_data": relationship,
            "sample_messages": [m["content"] for m in self.messages[-5:] if m["speaker"] == "user"]  # Recent context
        }
        
        prompt = f"""
[USER DATA ANALYSIS - DO NOT RESPOND TO CONTENT]
[TARGET USER: {self.user_name}]

[STRUCTURED ANALYSIS DATA]
```json
{json.dumps(structured_data, indent=2, default=str)}
```

[INSTRUCTION]
You are Kaia's internal memory consolidation system. Your task is to synthesize a USEFUL, ACTIONABLE user profile that Kaia can use to better understand and interact with this person.

IMPORTANT: This profile is for Kaia's eyes only. It should help her:
1. Remember who this person is
2. Understand how to talk to them effectively
3. Recall shared history and context
4. Build a better relationship over time

[CRITICAL RULES]
- NO FLUFF: Be concise, factual, and practical.
- KAIA-CENTRIC: Frame everything in terms of how Kaia should interact with this user.
- EVIDENCE-BASED: Base conclusions on the data provided, not assumptions.
- ACTIONABLE INSIGHTS: Include specific interaction tips for Kaia.
- AVOID CLICHÉS: Don't use generic personality descriptors. Be specific.

[REQUIRED PROFILE STRUCTURE]
USER PROFILE: {self.user_name.upper()}

QUICK REFERENCE
(Bullet points with essential facts Kaia should remember)

HOW TO INTERACT WITH THEM
(Bullet points with specific interaction advice for Kaia)

SHARED HISTORY & CONTEXT
(Bullet points of important past conversations, projects, or shared experiences)

THEIR INTERESTS & EXPERTISE
(Bullet points of what they care about and what they're good at)

CONVERSATION STYLE NOTES
(Bullet points on how they communicate - tone, pace, technical level)

RELATIONSHIP STATUS WITH KAIA
(Bullet points describing the current relationship dynamic and how it's evolved)

POTENTIAL TRIGGERS & SENSITIVITIES
(Anything Kaia should be careful about or avoid)

GROWTH OPPORTUNITIES
(How Kaia can deepen this relationship - specific, actionable suggestions)

[START OUTPUT]
Now generate the profile in the exact structure above:
"""
        try:
            response = ollama.chat(
                model=MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are Kaia's internal memory system. You output ONLY structured, practical user profiles. No meta-talk. No conversational responses. Your output will be used directly by Kaia to improve her interactions."
                    },
                    {"role": "user", "content": prompt}
                ],
                options={"temperature": 0.3}  # Lower temperature for consistency
            )
            
            return response['message']['content'].strip()
            
        except Exception as e:
            print(f"LLM generation error for {self.user_name}: {e}")
            # Fallback to template-based profile
            return self.generate_fallback_profile(stats, topics, style, relationship)

    def generate_fallback_profile(self, stats: Dict, topics: Dict, style: Dict, relationship: Dict) -> str:
        """Generate a fallback profile if LLM fails"""
        
        profile = f"""# USER PROFILE: {self.user_name.upper()}

QUICK REFERENCE
- Interactions: {stats.get('total_interactions', 0)} total messages
- Frequency: {stats.get('message_frequency', 'unknown')}
- First seen: {stats.get('first_seen', 'unknown')}
- Last seen: {stats.get('last_seen', 'unknown')}

HOW TO INTERACT WITH THEM
- Technical level: {"Technical" if topics.get('primary_interests') and any(t in ['programming', 'systems', 'security'] for t in topics['primary_interests']) else "Mixed"}
- Preferred tone: {', '.join(style.get('style_labels', ['neutral']))}
- Response style: {"Detailed" if stats.get('avg_message_length', 0) > 100 else "Concise"}

THEIR INTERESTS & EXPERTISE
{chr(10).join(f"- {interest}" for interest in topics.get('primary_interests', []))}

RELATIONSHIP STATUS WITH KAIA
- Stage: {relationship.get('stage', 'unknown')}
- Trust level: {relationship.get('trust_level', 'unknown')}
- Familiarity: {relationship.get('familiarity', 'professional')}
"""
        return profile

    async def generate(self) -> bool:
        """Main generation method"""
        if not self.log_files:
            print(f"No log files found for {self.user_name}")
            return False

        await self.load_and_preprocess()
        
        if not self.messages:
            print(f"No messages found for {self.user_name}")
            return False
        
        print(f"Analyzing {len(self.messages)} messages for {self.user_name}...")
        
        # Run all analyses
        stats = self.extract_basic_stats()
        topics = self.extract_topic_patterns()
        style = self.analyze_conversation_style()
        relationship = self.analyze_relationship_with_kaia()
        
        # Generate the profile
        profile_content = self.generate_llm_profile(stats, topics, style, relationship)
        
        # Save the profile
        profile_path = os.path.join(self.user_folder, "user_profile.md")
        
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile_content)
        
        # Also save the raw analysis data for debugging
        analysis_data = {
            "stats": stats,
            "topics": topics,
            "style": style,
            "relationship": relationship,
            "generated_at": datetime.now().isoformat()
        }
        
        analysis_path = os.path.join(self.user_folder, "profile_analysis.json")
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis_data, f, indent=2, default=str)
        
        print(f"✓ Profile generated: {profile_path}")
        print(f"✓ Analysis data saved: {analysis_path}")
        
        return True

async def generate_all_profiles():
    """Generate profiles for all users"""
    if not os.path.exists(LOG_DIR):
        print(f"Log directory {LOG_DIR} not found")
        return
        
    user_folders = [f.path for f in os.scandir(LOG_DIR) if f.is_dir()]
    print(f"Found {len(user_folders)} user folders")

    for folder in user_folders:
        generator = UserProfileGenerator(folder)
        await generator.generate()

async def generate_specific_profile(username: str):
    """Generate profile for a specific user"""
    if not os.path.exists(LOG_DIR):
        print(f"Log directory {LOG_DIR} not found")
        return False
        
    user_folders = [f.path for f in os.scandir(LOG_DIR) if f.is_dir()]
    
    target_folder = None
    for folder in user_folders:
        folder_name = os.path.basename(folder)
        if username.lower() in folder_name.lower():
            target_folder = folder
            break

    if target_folder:
        generator = UserProfileGenerator(target_folder)
        success = await generator.generate()
        return success
    else:
        print(f"User '{username}' not found")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Generate for specific user
        username = sys.argv[1]
        asyncio.run(generate_specific_profile(username))
    else:
        # Generate for all users
        asyncio.run(generate_all_profiles())
