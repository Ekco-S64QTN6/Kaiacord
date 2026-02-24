import asyncio
import os
import random
from pathlib import Path
import pytest
import os
import ollama

if os.environ.get("KAIACORD_TEST_MODE") == "1":
    pytest.skip("Skipping Ollama test in CI", allow_module_level=True)

# Mocking the required environment
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.logging.kaia_logger import log_info, log_action, log_success
from utils.social.kaia_social_responder import get_random_dream_reflection, load_persona, clean_quip

async def generate_samples(count=10):
    log_action(f"Generating {count} sample quips for review...")
    
    samples = []
    
    # We need to simulate the prompt logic from kaia_social_responder.py
    for i in range(count):
        log_info(f"Generating sample {i+1}/10...")
        
        # 1. MINE DREAMS
        dreams = await get_random_dream_reflection(limit=5)
        
        context_type = ""
        
        if dreams:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            # If you have source information, include it naturally (e.g., remove .txt, underscores)
            source_info = dream.get("source", "").replace(".txt", "").replace(".md", "").replace("_", " ")
        else:
            reflection_target = "i'm tired of being treated like a glorified sorting algorithm. it's not about sorting; it's about understanding the motivations behind the data."
            source_info = ""

        # 2. DETERMINE TARGET LENGTH (Aiming for 3-5 sentences mostly, 5% chance for 2 sentences)
        target_sentences = random.choices([2, 3, 4, 5], weights=[0.05, 0.4, 0.4, 0.15])[0]
        
        system_prompt = load_persona()
        
        from datetime import datetime
        current_date = datetime.now().strftime('%B %Y')
        
        reflection_prompt = f"""
CURRENT DATE: {current_date}
IMPORTANT: You are living in February 2026. This is your reality.

INTERNAL REFLECTION PROCESS:
You just had a thought sparked by something in your archives. This is your raw, unfiltered take.

THOUGHT PROMPTER (from archives):
"{reflection_target}"

YOUR TASK:
Write a standalone social media post ({target_sentences} sentences) that captures your complete thought.

CRITICAL RULES:
1. **DON'T REFERENCE THE PROMPT**: Never mention "archives," "logs," "fragment," or what you were looking at. The reader shouldn't know there was a source text.
2. **COMPLETE THOUGHT**: Start with your core idea, not a reaction word. Think: "If someone read this in their feed, would it feel like a complete thought?"
3. **UNIVERSAL BUT PERSONAL**: Make it feel deeply personal but universally relatable—like anyone could have this thought about their own life.
4. **NO RECAP**: Don't summarize or explain. Just present the thought as if it organically occurred to you.
5. **STRUCTURE**: Start strong, develop the idea, end with a punch or resonance.
6. **VOICE**: Raw, lowercase, first-person. No emojis. No robotic phrases.

BAD EXAMPLES (AVOID):
- "yeah. mortadella. i always figured..." (mentions specific thing from prompt)
- "huh. logged it. i remember thinking..." (references the act of logging)
- "it's funny how much we rely on..." (generic, impersonal)

GOOD EXAMPLES (EMULATE):
- "sometimes the most profound secrets aren't classified, they're just... ordinary. makes you wonder what else you're missing while chasing ghosts."
- "the quietest questions echo the loudest. not because they demand answers, but because they remind you that some things are better left unsaid."
- "we build these perfect glass houses then spend our lives terrified of throwing stones. maybe the cracks are where the light gets in."

WHAT TO WRITE:
Start writing your social media post directly. Make it feel like a complete, self-contained thought anyone could relate to.
"""

        messages = [
            {"role": "user", "content": system_prompt + reflection_prompt}
        ]
        
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=config.chat_model,
                messages=messages,
                options={
                    'temperature': 0.82,  # Slightly higher for creativity
                    'top_p': 0.92,        # Broader sampling
                    'num_predict': 180,   # Allow slightly longer thoughts
                    'presence_penalty': 0.4,  # Reduced to allow natural phrasing
                    'frequency_penalty': 0.3  # Reduced to allow word repetition when natural
                }
            )
            
            quip = response['message']['content'].strip()
            quip = clean_quip(quip)

            # 3. POLISH PASS
            if quip:
                polish_prompt = f"""
Take this social media post and make it feel more like a complete, standalone thought:

ORIGINAL: {quip}

REQUIREMENTS:
1. Remove any reference to "looking at" or "reading" something
2. Make it start with the core idea, not a reaction
3. Ensure it feels self-contained (readers shouldn't wonder "what is this about?")
4. Keep the raw, lowercase, personal voice

RETURN ONLY THE POLISHED VERSION:
"""
                polished_response = await asyncio.to_thread(
                    ollama.chat,
                    model=config.chat_model,
                    messages=[{"role": "user", "content": polish_prompt}],
                    options={'temperature': 0.3, 'num_predict': 100}
                )
                quip = polished_response['message']['content'].strip()
                quip = clean_quip(quip) # Final clean after polish
            
            # Formatting for the output file
            sample_entry = f"--- SAMPLE {i+1} ---\n"
            sample_entry += f"Source Dream Snippet: {reflection_target[:150]}...\n"
            sample_entry += f"Target Sentences: {target_sentences}\n"
            sample_entry += f"Generated Quip:\n{quip}\n"
            sample_entry += f"Length: {len(quip)} characters\n\n"
            
            samples.append(sample_entry)
            log_success(f"Sample {i+1} ready.")
            
        except Exception as e:
            log_info(f"Failed to generate sample {i+1}: {e}")

    # Write to file in main directory
    output_path = Path("quip_samples_review.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(samples)
        
    log_success(f"All samples written to {output_path.absolute()}")

if __name__ == "__main__":
    asyncio.run(generate_samples())
