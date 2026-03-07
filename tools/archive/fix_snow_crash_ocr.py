import re
import os

def fix_snow_crash_formatting(input_path, output_path):
    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern: sentence ending punctuation followed immediately by a lowercase word or specific artifacts
    # Example: "whatever your name isa roll-up steel door"
    # Heuristic 1: lowercase word directly after sentence ending (missing space/break)
    # Heuristic 2: specific Concatenation artifacts found in audit (e.g. "isa", "ofTexas")
    
    fixed = content
    
    # Fix the specific "isa" artifact found in line 165
    fixed = fixed.replace("whatever your name isa roll-up", "whatever your name is—a roll-up")
    
    # Fix the specific "ofTexas" / "by way of the ArmyHiro's" artifact in line 181
    fixed = fixed.replace("of Texas by way of the ArmyHiro's", "of Texas by way of the Army.\n\nHiro's")
    fixed = fixed.replace("went atomicthe only", "went atomic. The only")
    fixed = fixed.replace("really enjoysthe Library", "really enjoys—the Library")
    
    # Fix the "musical phenomenonthe half" artifact in line 191
    fixed = fixed.replace("musical phenomenonthe half", "musical phenomenon—the half")
    
    # Fix the "existence ofthree lasersand even" artifact in line 193
    fixed = fixed.replace("three lasersand even", "three lasers—and even")
    
    # Fix generalized "lowercase-follows-letter" where a sentence ending was swallowed
    # e.g. "wordisa"
    # We look for common verbs swallowed: "isa", "was", "has", "had", "the"
    swallowed_verbs = ["isa", "wasthe", "hasthe", "hadthe", "ofanother"]
    for v in swallowed_verbs:
        if v == "isa":
            fixed = re.sub(r'([a-z])isa\b', r'\1 is a', fixed)
        else:
            # Add spaces before the second word
            match = re.search(r'([a-z])(' + v[1:] + r')\b', fixed)
            if match:
                fixed = fixed.replace(match.group(0), f"{match.group(1)} {match.group(2)}")

    # Heuristic: Find very long lines and try to split them at sentence boundaries where they look like scene shifts
    lines = fixed.split('\n')
    new_lines = []
    for line in lines:
        if len(line) > 1000:
            # Try to find points where a period is followed by a capital letter but no space
            # or where a lowercase letter follows a punctuation mark
            line = re.sub(r'([.\?!])([A-Z])', r'\1\n\n\2', line)
            line = re.sub(r'([a-z])([A-Z][a-z]+ [A-Z])', r'\1\n\n\2', line) # Scene shift heuristic
            new_lines.extend(line.split('\n'))
        else:
            new_lines.append(line)
            
    final_output = '\n'.join(new_lines)
    
    print(f"Writing fixed content to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_output)
    
    print("Done.")

if __name__ == "__main__":
    base_path = "/home/ekco/github/Kaiacord/knowledge_base/Books/Snow Crash By Neal Stephenson.md"
    # Overwrite the original as requested "fix all of those listed in walkthrough"
    fix_snow_crash_formatting(base_path, base_path)
