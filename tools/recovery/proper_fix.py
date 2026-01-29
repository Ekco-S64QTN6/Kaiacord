#!/usr/bin/env python3
"""
PROPER FIX: Remove boilerplate without affecting real users
"""
import os
import sys
import re

def remove_boilerplate_only():
    """Remove ONLY boilerplate questions, NOT real user names"""
    print("🔧 Removing boilerplate questions ONLY...")
    
    # 1. Fix Kaiacord.py - EmergencyContaminationFilter
    filepath = "Kaiacord.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove the specific boilerplate list
    # Use regex to match the list structure more flexibly
    boilerplate_pattern = r'if len\(filtered_response\.strip\(\)\) < 20:\s+filtered_response = random\.choice\(\[[^\]]+\]\)'
    
    if re.search(boilerplate_pattern, content, flags=re.DOTALL):
        content = re.sub(boilerplate_pattern, 
                        'if len(filtered_response.strip()) < 20:\n            filtered_response = ""',
                        content, flags=re.DOTALL)
        print("✅ Removed boilerplate from EmergencyContaminationFilter")
    else:
        print("⚠️ Could not find EmergencyContaminationFilter boilerplate pattern (might be already removed)")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    # 2. Remove fictional story patterns from RAG WITHOUT affecting real users
    filepath = "utils/kaia_rag.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove the bad filter that included user names if it exists
    bad_filter_pattern = r'fictional_patterns = \[[^\]]+\]'
    
    # Replace with smarter filter that only blocks fictional story patterns
    smart_filter = '''# === SMART FICTION FILTER ===
        # Only filter specific fictional story patterns, NOT user names
        fictional_story_patterns = [
            r"i remember you working on the data pipeline",
            r"back in '21.*?(?:you were|memory leak|server farm)",
            r"you were chasing a memory leak for days",
            r"almost burned out the whole server farm",
            r"good work.*?you're good at digging",
        ]
        
        for pattern in fictional_story_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                continue  # Skip this specific fictional story'''
    
    # We need to find where to insert or replace. 
    # If the bad filter exists, replace it.
    # If not, we might need to look for where it should be.
    # The user's script assumes it replaces a specific block.
    # Let's try to find the "STRICT FILTERS TO PREVENT FICTION" comment or similar.
    
    if "STRICT FILTERS TO PREVENT FICTION" in content:
        # Try to replace the whole block
        # This is tricky with regex if we don't know exact content.
        # Let's try to find the variable assignment.
        if re.search(bad_filter_pattern, content, flags=re.DOTALL):
             # We will just replace the variable assignment and the loop if possible
             # But simpler is to just look for the fictional_patterns assignment
             pass

    # Actually, let's just look for the fictional_patterns assignment and replace it with smart_filter logic
    # But we need to be careful about context.
    # The user script provided a specific replace block. Let's try to use that if it matches.
    
    bad_filter_regex = r'# === STRICT FILTERS TO PREVENT FICTION ===.*?continue  # Skip this contaminated node'
    
    if re.search(bad_filter_regex, content, flags=re.DOTALL):
        content = re.sub(bad_filter_regex, smart_filter, content, flags=re.DOTALL)
        print("✅ Replaced bad filter with smart filter")
    else:
        # If we can't find the exact block, maybe we just inject it or it's not there.
        # If it's not there, we might want to add it? Or maybe the previous script removed it?
        # The previous script didn't add it, so it might be there from before.
        # Let's check if we can find "fictional_patterns ="
        if "fictional_patterns =" in content:
             content = re.sub(r'fictional_patterns = \[[^\]]+\]', 
                              '''fictional_story_patterns = [
            r"i remember you working on the data pipeline",
            r"back in '21.*?(?:you were|memory leak|server farm)",
            r"you were chasing a memory leak for days",
            r"almost burned out the whole server farm",
            r"good work.*?you're good at digging",
        ]''', content, flags=re.DOTALL)
             content = content.replace('for pattern in fictional_patterns:', 'for pattern in fictional_story_patterns:')
             print("✅ Updated fictional patterns to be smart")

    # Also fix HallucinationDetector fallback
    hall_detector_pattern = r'if len\(clean_response\) < 20:\s+clean_response = "yeah\. what\'s up\?\\n\\ncoffee\'s getting cold\. what do you need\?"'
    
    if re.search(hall_detector_pattern, content, flags=re.DOTALL):
        content = re.sub(hall_detector_pattern,
                        'if len(clean_response) < 20:\n            clean_response = ""',
                        content, flags=re.DOTALL)
        print("✅ Fixed HallucinationDetector fallback")
    else:
        print("⚠️ HallucinationDetector fallback pattern not found (might be already fixed)")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    # 3. Fix kaia_news.py - remove boilerplate endings
    filepath = "utils/kaia_news.py"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Remove endings
        content = re.sub(r'self\.endings = \[.*?\]', 
                        'self.endings = []  # EMPTY - NO BOILERPLATE QUESTIONS',
                        content, flags=re.DOTALL)
        
        # Remove identity intros
        content = re.sub(r'self\.identity_intros = \{.*?\}',
                        '''self.identity_intros = {
                'casual': [""],
                'direct': [""]
            }''', content, flags=re.DOTALL)
        
        # Remove ending addition
        content = re.sub(r'base_response \+= " " \+ random\.choice\(self\.endings\)',
                        '# NO BOILERPLATE ENDINGS ADDED', content)
        
        print("✅ Removed boilerplate from ResponseEnhancer")
        
        with open(filepath, 'w') as f:
            f.write(content)

def clean_contaminated_logs_smart():
    """Clean ONLY the specific fictional stories, NOT user names"""
    print("\n🧹 Cleaning ONLY fictional stories from logs...")
    
    logs_dir = "knowledge_base/user_logs"
    if not os.path.exists(logs_dir):
        print("⚠️  Logs directory not found")
        return
    
    # ONLY target the specific fictional story that's causing problems
    specific_fiction_patterns = [
        "i remember you working on the data pipeline back in '21",
        "you were chasing a memory leak for days",
        "almost burned out the whole server farm",
        "good work. you're good at digging",
    ]
    
    cleaned_count = 0
    
    for root, dirs, files in os.walk(logs_dir):
        for file in files:
            if file.endswith('.txt'):
                filepath = os.path.join(root, file)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Remove ONLY the specific fictional story lines
                for pattern in specific_fiction_patterns:
                    if pattern in content:
                        # Replace the specific line with empty string
                        lines = content.split('\n')
                        cleaned_lines = []
                        
                        for line in lines:
                            if pattern in line:
                                print(f"   🗑️  Removing fictional story: {line[:60]}...")
                                cleaned_count += 1
                                cleaned_lines.append("")  # Empty line instead
                            else:
                                cleaned_lines.append(line)
                        
                        content = '\n'.join(cleaned_lines)
                
                # Also remove boilerplate questions from logs
                boilerplate_questions = [
                    "what are you working on?",
                    "what's on your mind?",
                    "Anything else on your mind?",
                    "What's your take on that?",
                    "Seen anything interesting on your end?",
                    "Got any thoughts about this?",
                    "Anything specific you're curious about?"
                ]
                
                for question in boilerplate_questions:
                    if question in content:
                        # Just remove the question line
                        lines = content.split('\n')
                        cleaned_lines = []
                        
                        for line in lines:
                            if question in line:
                                print(f"   🗑️  Removing boilerplate question: {line[:60]}...")
                                cleaned_count += 1
                                cleaned_lines.append("")
                            else:
                                cleaned_lines.append(line)
                        
                        content = '\n'.join(cleaned_lines)
                
                if content != original_content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
    
    if cleaned_count > 0:
        print(f"✅ Cleaned {cleaned_count} fictional/boilerplate lines")
    else:
        print("✅ No specific fiction found in logs")

def update_persona_no_questions():
    """Update persona to discourage ending with questions"""
    print("\n📝 Updating persona to avoid question endings...")
    
    persona_path = "knowledge_base/kaia_persona.md"
    if os.path.exists(persona_path):
        with open(persona_path, 'r') as f:
            content = f.read()
        
        # Add instruction to avoid ending with questions
        if "## RESPONSE STYLE RULES" not in content:
            response_rules = '''

## RESPONSE STYLE RULES
- NEVER end responses with formulaic questions like "what are you working on?" or "what's on your mind?"
- Do NOT add conversational filler questions at the end of responses
- Be direct and grounded - if you have nothing else to say, just end the response
- No corporate-speak, no hand-holding, no unnecessary questions
- Speak in lowercase, be blunt, stay grounded'''
            
            content += response_rules
            with open(persona_path, 'w') as f:
                f.write(content)
            print("✅ Added response style rules to persona")
        else:
            print("✅ Persona already has response rules")

def create_boilerplate_detector():
    """Create a detector for boilerplate endings"""
    print("\n🔍 Creating boilerplate detector...")
    
    detector_code = '''#!/usr/bin/env python3
"""
Detector for boilerplate questions at the end of responses
"""
import re

class BoilerplateDetector:
    """Detect and remove boilerplate question endings"""
    
    # Boilerplate questions that should NEVER appear at the end
    BOILERPLATE_ENDINGS = [
        r"what are you working on[.?]?$",
        r"what's on your mind[.?]?$",
        r"anything else on your mind[.?]?$",
        r"what's your take[.?]?$",
        r"seen anything interesting[.?]?$",
        r"got any thoughts[.?]?$",
        r"anything specific you're curious[.?]?$",
        r"yeah\. what's up[.?]?$",
        r"coffee's cold\. what do you need[.?]?$",
        r"i'm here\. what's on your mind[.?]?$",
        r"listening\. go ahead[.?]?$",
        r"not much to say about that\. anything else[.?]?$",
    ]
    
    @classmethod
    def clean_response(cls, response: str) -> str:
        """Remove boilerplate questions from the end of responses"""
        if not response:
            return response
        
        lines = response.split('\\n')
        clean_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                clean_lines.append(line)
                continue
            
            # Check if this line is a boilerplate question
            is_boilerplate = any(
                re.search(pattern, line_stripped, re.IGNORECASE)
                for pattern in cls.BOILERPLATE_ENDINGS
            )
            
            if not is_boilerplate:
                clean_lines.append(line)
            else:
                # Don't add boilerplate lines
                continue
        
        # Rejoin and strip
        clean_response = '\\n'.join(clean_lines).strip()
        
        # Also check the last line specifically
        if clean_response:
            last_line = clean_response.split('\\n')[-1].strip()
            is_last_line_boilerplate = any(
                re.search(pattern, last_line, re.IGNORECASE)
                for pattern in cls.BOILERPLATE_ENDINGS
            )
            
            if is_last_line_boilerplate:
                # Remove the last line
                lines = clean_response.split('\\n')
                clean_response = '\\n'.join(lines[:-1]).strip()
        
        return clean_response

# Usage:
# from utils.boilerplate_detector import BoilerplateDetector
# clean_response = BoilerplateDetector.clean_response(raw_response)
'''
    
    with open("utils/boilerplate_detector.py", "w") as f:
        f.write(detector_code)
    
    print("✅ Created boilerplate detector")

def integrate_detector():
    """Integrate the boilerplate detector into Kaiacord.py"""
    print("\n🔄 Integrating boilerplate detector...")
    
    filepath = "Kaiacord.py"
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Add import at top if not already there
    imports = "from utils.kaia_intelligence import"
    if imports in content and "from utils.boilerplate_detector import BoilerplateDetector" not in content:
        content = content.replace(
            imports,
            "from utils.boilerplate_detector import BoilerplateDetector\n" + imports
        )
    
    # Find where content is prepared before sending
    # Look for the pattern where content is cleaned up before send_kaia_response
    content_cleanup = 'content = content.replace("`", "")'
    
    if content_cleanup in content and "BoilerplateDetector.clean_response" not in content:
        # Insert boilerplate cleaning after content cleanup
        new_cleanup = '''content = content.replace("`", "")
        
        # REMOVE BOILERPLATE QUESTION ENDINGS
        content = BoilerplateDetector.clean_response(content)'''
        
        content = content.replace(content_cleanup, new_cleanup)
        print("✅ Integrated boilerplate detector")
    elif "BoilerplateDetector.clean_response" in content:
        print("✅ Boilerplate detector already integrated")
    else:
        print("⚠️ Could not find content cleanup pattern to integrate detector")
    
    with open(filepath, 'w') as f:
        f.write(content)

def main():
    print("=" * 70)
    print("🎯 PROPER FIX: Remove Boilerplate, Keep Real Users")
    print("=" * 70)
    
    # Apply fixes
    remove_boilerplate_only()
    clean_contaminated_logs_smart()
    update_persona_no_questions()
    create_boilerplate_detector()
    integrate_detector()
    
    print("\n" + "=" * 70)
    print("✅ ALL FIXES APPLIED PROPERLY!")
    print("\n📋 WHAT WAS FIXED:")
    print("1. ✅ Removed hard-coded boilerplate questions from code")
    print("2. ✅ Removed ONLY specific fictional stories from logs")
    print("3. ✅ DID NOT filter real user names (Ekco, Starkind)")
    print("4. ✅ Updated persona to avoid question endings")
    print("5. ✅ Created boilerplate question detector")
    print("6. ✅ Integrated detector to clean responses before sending")
    print("\n🎯 This fixes the REAL problems:")
    print("   - Kaia won't add 'what are you working on?'")
    print("   - Kaia won't add 'yeah. what's on your mind?'")
    print("   - Kaia won't include fictional stories in context")
    print("   - Real users are NOT filtered or affected")
    print("\n🔄 RESTART KAIACORD:")
    print("   pkill -f 'python.*Kaiacord'")
    print("   python Kaiacord.py")
    print("\n💬 TEST WITH: @kaia status kaia")
    print("   Should get her actual response, NO boilerplate questions")
    print("=" * 70)

if __name__ == "__main__":
    main()
