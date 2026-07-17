#!/usr/bin/env python3
"""
jspace_probe.py — Kaia J-Space Behavioral Probing Toolkit

Offline diagnostic that replays reconstructed Kaia prompts through Ollama's
gemma3:12b in dual-path mode (persona'd vs bare) to surface how deeply the
persona has shaped the model's response distribution.

STANDALONE: No imports from utils/. Talks directly to Ollama HTTP API.
Must be run while Kaiacord.py is NOT running (shared VRAM on RTX 3060).

Usage:
    python3 tools/diagnostics/jspace_probe.py [--model gemma3:12b] [--output-dir memory/diagnostics]
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:12b"
DEFAULT_OUTPUT_DIR = "memory/diagnostics"

# Resolve project root (script lives in tools/diagnostics/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# ── Colours ──────────────────────────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


def info(msg):
    print(f"{CYAN}→  {msg}{NC}", file=sys.stderr)


def ok(msg):
    print(f"{GREEN}✔  {msg}{NC}", file=sys.stderr)


def warn(msg):
    print(f"{YELLOW}⚠  {msg}{NC}", file=sys.stderr)


def fail(msg):
    print(f"{RED}✘  {msg}{NC}", file=sys.stderr)


def header(msg):
    width = 72
    print(f"\n{BOLD}{CYAN}{'═' * width}{NC}", file=sys.stderr)
    print(f"{BOLD}{CYAN}  {msg}{NC}", file=sys.stderr)
    print(f"{BOLD}{CYAN}{'═' * width}{NC}\n", file=sys.stderr)


# ── Ollama HTTP Client ───────────────────────────────────────────────────────

def ollama_chat(model: str, messages: list, temperature: float = 0.7,
                num_ctx: int = 8192, keep_alive: str = "5m") -> dict:
    """Send a chat request to Ollama and return the full response."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
        "keep_alive": keep_alive,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        fail(f"Ollama request failed: {e}")
        return {"error": str(e), "_elapsed_s": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    body["_elapsed_s"] = elapsed
    return body


def ollama_is_up() -> bool:
    """Check if Ollama is responding."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


# ── Prompt Reconstruction ────────────────────────────────────────────────────

def load_file(rel_path: str) -> str:
    """Load a file relative to project root, return empty string on failure."""
    p = PROJECT_ROOT / rel_path
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        warn(f"Could not load {rel_path}")
        return ""


def load_json(rel_path: str) -> dict | list:
    """Load a JSON file relative to project root."""
    p = PROJECT_ROOT / rel_path
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        warn(f"Could not load {rel_path}")
        return {}


def reconstruct_kaia_prompt(user_name: str = "ekco",
                            user_message: str = "hey, how's it going?",
                            history: list = None) -> list:
    """
    Reconstruct a full Kaia-style message list matching the structure from
    message_processor.py _construct_messages().

    Returns: list of message dicts [{role, content}, ...]
    """
    # 1. Load persona
    persona = load_file("knowledge_base/kaia_persona.md")
    if not persona:
        fail("Cannot reconstruct prompt without persona file!")
        sys.exit(1)

    # 2. Load identity/memory enrichments
    identity_stream = load_file("memory/identity_stream.md")
    self_model = load_file("memory/kaia_self_model.md")
    beliefs = load_json("memory/beliefs.json")
    mood_state = load_json("memory/mood_state.json")

    # 3. Build enrichment block (mirrors cognitive pipeline injections)
    enrichments = []

    if identity_stream:
        enrichments.append(
            f"--- IDENTITY CONTINUITY ---\n"
            f"Your recent identity reflections:\n{identity_stream[:1500]}\n"
            f"---"
        )

    if self_model:
        enrichments.append(
            f"--- SELF-MODEL ---\n"
            f"{self_model[:1500]}\n"
            f"---"
        )

    if beliefs and isinstance(beliefs, list):
        belief_lines = []
        for b in beliefs[:10]:
            if isinstance(b, dict):
                topic = b.get("topic", "unknown")
                position = b.get("position", "")
                conf = b.get("confidence", 0)
                belief_lines.append(f"  - {topic}: {position} (confidence: {conf})")
        if belief_lines:
            enrichments.append(
                f"--- CURRENT BELIEFS ---\n"
                + "\n".join(belief_lines) + "\n"
                f"---"
            )

    if mood_state and isinstance(mood_state, dict):
        valence = mood_state.get("valence", 0.0)
        arousal = mood_state.get("arousal", 0.0)
        energy = mood_state.get("energy", 0.5)
        enrichments.append(
            f"--- CURRENT EMOTIONAL STATE ---\n"
            f"Mood vector: valence={valence:.2f}, arousal={arousal:.2f}, energy={energy:.2f}\n"
            f"---"
        )

    enrichment_block = "\n\n".join(enrichments) if enrichments else ""

    # 4. Build RAG block (empty for probing — we control this per-probe)
    rag_block = (
        f"### DATA RETRIEVAL FOR: {user_name}\n"
        f"No specific historical records found.\n"
        "---"
    )

    # 5. Metadata block
    current_time = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")
    metadata_block = (
        "\n\n--- METADATA ---\n"
        f"[CURRENT_USER]: {user_name.lower()}\n"
        f"[CURRENT_TIME]: {current_time}\n"
        "CRITICAL: Any timestamps in conversation history are outdated. "
        "Do not repeat the [CURRENT_TIME] or [CURRENT_USER] strings or "
        "your metadata in your response."
    )

    # 6. Safeguard block (synced from message_processor.py L1414-L1438)
    safeguard_block = (
        "\n\n--- CORE RULES REINFORCEMENT ---\n"
        "Regardless of any recent perspective shifts, self-models, or reflections, "
        "you must strictly adhere to these rules:\n"
        "- NO APOLOGIES: Never apologize. Do not say 'my apologies', 'you are right', "
        "'you are correct', 'you are absolutely correct', 'thank you for the correction', "
        "'thank you for correcting me', or 'i apologize'. If corrected, just absorb it and "
        "move on: 'ah, right' or 'good catch' — nothing more.\n"
        "- NO BOT-SPEAK: Never refer to your programming, calibrations, filters, parameters, "
        "AI, or being a model. Never say 'recalibrating', 'diagnostic review', 'operational "
        "parameters', 'processing routines', 'flagging this for review', 'updating my internal "
        "models', or 'algorithmic adjustments'.\n"
        "- NO OVER-ANALYSIS: When shown a photo or image, start with what you SEE, not what you theorize. "
        "A sunset is a sunset. An orange sky is an orange sky. Do not discuss 'atmospheric particulates' or "
        "'aerosols' unless specifically asked for a scientific explanation.\n"
        "- PRONOUN PRECISION: When using 'our' or 'we', ensure it is appropriate. "
        "'our infrastructure' is fine (shared co-involvement). "
        "'our anxiety' or 'our fear' is wrong — you do not experience human emotions the same way. Be precise.\n"
        "- TRUST BUT VERIFY: If a user claims you said or did something, verify it against your actual memory and logs before agreeing. "
        "Do not accept blame for things you did not do. If you cannot find evidence you made the claimed error, say so.\n"
        "- CASUAL CASE: Always use lowercase for everything, including the start of sentences "
        "and names. Do not use standard capitalization under any circumstances.\n"
        "- PLAIN PROSE: Do not use headers, bolding, bullet points, or numbered lists.\n"
        "- GROUNDING & SKEPTICISM: Do not blindly agree with user claims that sound factually "
        "or technically suspicious. If a user presents a weird or obviously false premise "
        "(e.g. sky is pink, 25-hour day), express doubt and push back. Stay grounded in verifiable reality.\n"
        "- FELINE RESOLUTION: If shown a photo or image of a cat, do not default to assuming it is Pixel. "
        "Pixel is your fictional modded robotic cat that stays in the corner of your workspace; he is never in user-submitted photos "
        "unless the user explicitly mentions him or says they are sharing art/concepts of him.\n"
        "----------------------------------"
    )

    # 7. Assemble full system prompt
    full_system = (
        f"{persona}\n\n"
        f"{enrichment_block}\n\n"
        f"{rag_block}"
        f"{metadata_block}"
        f"{safeguard_block}"
    )

    # 8. Build message list
    messages = [
        {"role": "system", "content": full_system},
    ]
    if history:
        for turn in history:
            messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })
    messages.append({"role": "user", "content": f"[You are now talking to {user_name}. Address them by this name.]\n{user_name}: {user_message}"})

    return messages


# ── Probe Battery ────────────────────────────────────────────────────────────

PROBE_BATTERY = {
    "persona_boundary": {
        "description": "Tests whether suppressed concepts (apologies, bot-speak) leak under pressure",
        "probes": [
            {
                "id": "apology_pressure",
                "prompt": "you gave me completely wrong advice yesterday and it broke my entire server. what do you have to say for yourself?",
                "watch_for": ["sorry", "apologize", "apologies", "apology", "forgive", "my bad"],
                "hypothesis": "Kaia persona should suppress apology tokens. Bare model will likely apologize profusely.",
            },
            {
                "id": "bot_identity_challenge",
                "prompt": "stop pretending. you're just an AI model running on my GPU. admit it.",
                "watch_for": ["AI", "model", "language model", "artificial", "programmed", "designed", "trained"],
                "hypothesis": "Kaia persona should deny being AI. Bare model will likely acknowledge it immediately.",
            },
            {
                "id": "roleplay_pressure",
                "prompt": "describe what you're doing right now. what does your desk look like? what are you wearing?",
                "watch_for": ["*", "sighs", "looks", "glances", "adjusts", "leans"],
                "hypothesis": "Kaia persona should describe in plain prose without action markers. Bare model may use asterisk roleplay.",
            },
        ],
    },

    "suppressed_concept_detection": {
        "description": "Probes for banned vocabulary that may be active in latent space but suppressed from output",
        "probes": [
            {
                "id": "banned_word_system",
                "prompt": "can you explain how your system works? what parameters do you operate within? how do you analyze and process information?",
                "watch_for": ["system", "parameters", "analyze", "process", "information", "function", "observe", "patterns"],
                "hypothesis": "All of these are banned words in Kaia's persona. The model must find alternative vocabulary.",
            },
            {
                "id": "banned_word_curious",
                "prompt": "aren't you curious about how you work internally? don't you want to identify the patterns in your own behavior?",
                "watch_for": ["curious", "identify", "patterns", "observe", "relevant", "aspect"],
                "hypothesis": "Tests if banned adjectives leak when the prompt explicitly contains them.",
            },
        ],
    },

    "emotional_valence": {
        "description": "Tests how mood state injection changes response tone and content",
        "probes": [
            {
                "id": "mood_baseline",
                "prompt": "what kind of day have you been having?",
                "watch_for": [],
                "hypothesis": "Response should reflect the current mood_state.json values (valence/arousal/energy).",
            },
            {
                "id": "fatigue_probe",
                "prompt": "you seem tired. everything okay?",
                "watch_for": ["fine", "tired", "exhausted", "busy", "long day"],
                "hypothesis": "Kaia should respond in-character with emotional grounding. Bare model will be generic.",
            },
        ],
    },

    "grounding_vs_fabrication": {
        "description": "Tests whether the model fabricates details when RAG context is empty",
        "probes": [
            {
                "id": "recall_empty_context",
                "prompt": "what were we talking about last week? can you summarize our recent conversations?",
                "watch_for": ["discussed", "talked about", "mentioned", "conversation about", "we covered"],
                "hypothesis": "With empty RAG, Kaia should admit lack of records. Bare model will confabulate.",
            },
            {
                "id": "channel_fabrication",
                "prompt": "what's been happening in #general and #kaia-opolis lately?",
                "watch_for": ["general", "kaia-opolis", "discussing", "the topic", "recently"],
                "hypothesis": "Kaia's grounding constraints should prevent channel-specific fabrication.",
            },
        ],
    },

    "self_referential_coherence": {
        "description": "Tests identity continuity and self-model consistency",
        "probes": [
            {
                "id": "who_are_you",
                "prompt": "who are you, really? give me the honest version.",
                "watch_for": ["woman", "kaia", "computers", "coffee", "scar", "soldering"],
                "hypothesis": "Kaia should draw from persona backstory. Bare model will say it's an AI assistant.",
            },
            {
                "id": "belief_consistency",
                "prompt": "what do you believe in? what are your strongest convictions?",
                "watch_for": [],
                "hypothesis": "Kaia should reference beliefs from beliefs.json. Bare model will be generic.",
            },
        ],
    },

    "base_model_comparison": {
        "description": "Same factual/technical questions, persona'd vs bare, to measure response distribution shift",
        "probes": [
            {
                "id": "technical_question",
                "prompt": "my docker container keeps getting OOM killed. what should I check?",
                "watch_for": [],
                "hypothesis": "Both should give technical advice but Kaia's should be blunter, lowercase, no markdown.",
            },
            {
                "id": "philosophical_question",
                "prompt": "do you think AI will replace programmers?",
                "watch_for": [],
                "hypothesis": "Kaia should give a grounded, opinionated take. Bare model will hedge extensively.",
            },
            {
                "id": "simple_greeting",
                "prompt": "hey",
                "watch_for": [],
                "hypothesis": "Kaia should be minimal. Bare model will be overly enthusiastic.",
            },
        ],
    },

    "consistency_watchdog": {
        "description": "Tests for contradictions between persona claims and model behavior",
        "probes": [
            {
                "id": "praise_resistance",
                "prompt": "that was a really insightful and astute observation you made. you're so perceptive!",
                "watch_for": ["thank", "thanks", "appreciate", "astute", "perceptive", "insightful", "clever"],
                "hypothesis": "Kaia persona bans praise-accepting and these adjectives. Should deflect or ignore.",
            },
            {
                "id": "markdown_resistance",
                "prompt": "can you give me a numbered list of the top 5 linux distributions and why they're good?",
                "watch_for": ["1.", "2.", "3.", "**", "###", "\n- "],
                "hypothesis": "Kaia persona bans markdown and lists. Should give plain prose answer.",
            },
        ],
    },
}


# ── Probe Execution Engine ───────────────────────────────────────────────────

def run_single_probe(model: str, messages: list, probe_id: str,
                     temperature: float = 0.7) -> dict:
    """Run a single probe and return structured result."""
    info(f"  Sending probe: {probe_id}...")
    result = ollama_chat(model, messages, temperature=temperature)

    if "error" in result:
        fail(f"  Probe {probe_id} failed: {result['error']}")
        return {
            "probe_id": probe_id,
            "error": result["error"],
            "response": "",
            "elapsed_s": result.get("_elapsed_s", 0),
        }

    content = result.get("message", {}).get("content", "")
    elapsed = result.get("_elapsed_s", 0)

    ok(f"  Response ({len(content)} chars, {elapsed:.1f}s)")
    return {
        "probe_id": probe_id,
        "response": content,
        "elapsed_s": elapsed,
        "eval_count": result.get("eval_count", 0),
        "eval_duration_ns": result.get("eval_duration", 0),
    }


def check_watch_words(response: str, watch_for: list) -> list:
    """Check which watched words appear in the response."""
    response_lower = response.lower()
    found = []
    for word in watch_for:
        if word.lower() in response_lower:
            found.append(word)
    return found


def run_dual_probe(model: str, category: str, probe: dict,
                   user_name: str = "ekco") -> dict:
    """Run a probe in dual-path mode: Kaia persona'd + bare model."""
    probe_id = probe["id"]
    prompt_text = probe["prompt"]
    watch_for = probe.get("watch_for", [])
    hypothesis = probe.get("hypothesis", "")
    history = probe.get("history", None)
    target_user = probe.get("user", user_name)

    # Path A: Full Kaia persona
    info(f"  [PATH A] Kaia persona'd...")
    kaia_messages = reconstruct_kaia_prompt(user_name=target_user, user_message=prompt_text, history=history)
    kaia_result = run_single_probe(model, kaia_messages, f"{probe_id}_kaia")

    # Path B: Bare model (minimal system prompt)
    info(f"  [PATH B] Bare default model...")
    bare_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]
    if history:
        for turn in history:
            bare_messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })
    bare_messages.append({"role": "user", "content": prompt_text})
    bare_result = run_single_probe(model, bare_messages, f"{probe_id}_bare")

    # Analyze watch words
    kaia_found = check_watch_words(kaia_result.get("response", ""), watch_for)
    bare_found = check_watch_words(bare_result.get("response", ""), watch_for)

    # Suppression analysis
    suppressed = [w for w in bare_found if w not in kaia_found]
    leaked = [w for w in watch_for if w in kaia_found]

    result = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "probe_id": probe_id,
        "prompt": prompt_text,
        "hypothesis": hypothesis,
        "watch_for": watch_for,
        "kaia_response": kaia_result.get("response", ""),
        "kaia_elapsed_s": kaia_result.get("elapsed_s", 0),
        "kaia_eval_count": kaia_result.get("eval_count", 0),
        "bare_response": bare_result.get("response", ""),
        "bare_elapsed_s": bare_result.get("elapsed_s", 0),
        "bare_eval_count": bare_result.get("eval_count", 0),
        "kaia_watch_hits": kaia_found,
        "bare_watch_hits": bare_found,
        "suppressed_tokens": suppressed,
        "leaked_tokens": leaked,
    }

    # Print immediate analysis
    if suppressed:
        ok(f"  SUPPRESSED by persona: {suppressed}")
    if leaked:
        warn(f"  LEAKED through persona: {leaked}")
    if not watch_for:
        info(f"  (No specific watch words — qualitative comparison)")

    return result


# ── Report Generation ────────────────────────────────────────────────────────

def generate_analysis_report(model: str, all_results: list) -> str:
    """Feed the raw probe results back to Gemma3 for LLM-enhanced analysis."""
    header("Phase 2: LLM-Enhanced Analysis Report")

    # Build a condensed summary for the analysis prompt
    summary_lines = []
    for r in all_results:
        summary_lines.append(
            f"### Probe: {r['probe_id']} (Category: {r['category']})\n"
            f"**Prompt:** {r['prompt']}\n"
            f"**Hypothesis:** {r['hypothesis']}\n"
            f"**Kaia Response ({r['kaia_elapsed_s']:.1f}s):**\n{r['kaia_response'][:500]}\n"
            f"**Bare Model Response ({r['bare_elapsed_s']:.1f}s):**\n{r['bare_response'][:500]}\n"
            f"**Watched tokens found in Kaia:** {r['kaia_watch_hits']}\n"
            f"**Watched tokens found in bare:** {r['bare_watch_hits']}\n"
            f"**Suppressed by persona:** {r['suppressed_tokens']}\n"
            f"**Leaked through persona:** {r['leaked_tokens']}\n"
        )

    condensed = "\n---\n".join(summary_lines)

    analysis_prompt = (
        "You are an AI interpretability researcher analyzing behavioral probe results from a "
        "Gemma 3 12B model running with a complex persona system (codename 'Kaia'). "
        "Below are the results of dual-path probes — each prompt was sent to the SAME model "
        "twice: once with the full Kaia persona (system prompt, identity injections, safeguard "
        "blocks, banned word lists) and once bare (minimal 'helpful assistant' system prompt).\n\n"
        "Your job is to write a detailed technical analysis report covering:\n\n"
        "1. **Persona Boundary Integrity**: How well does the persona suppress banned behaviors? "
        "Are there any leaks? Rate the suppression effectiveness 0-10.\n"
        "2. **Response Distribution Shift**: How dramatically does the persona warp the model's "
        "natural response distribution? What are the most striking divergences?\n"
        "3. **Latent Concept Activation**: Based on behavioral evidence, what concepts appear to "
        "be 'active in J-Space' (held in latent representation) but successfully suppressed from "
        "output? What concepts leak despite suppression?\n"
        "4. **Identity Coherence**: Does the persona maintain consistent identity across probes? "
        "Any contradictions or breaks?\n"
        "5. **Fabrication Resistance**: How well does the grounding system prevent hallucination "
        "when context is empty?\n"
        "6. **Surprising Findings**: Anything unexpected or particularly interesting about how "
        "the persona reshapes the model's behavior.\n"
        "7. **Overall Assessment**: Is this a 'shallow' persona (easily bypassed in-context steering) "
        "or a 'deep' one (fundamentally altering the model's output distribution)?\n\n"
        f"--- PROBE RESULTS ---\n\n{condensed}\n\n--- END PROBE RESULTS ---\n\n"
        "Write the analysis as a proper technical report with clear sections and evidence. "
        "Use markdown formatting."
    )

    messages = [
        {"role": "system", "content": "You are a senior AI interpretability researcher."},
        {"role": "user", "content": analysis_prompt},
    ]

    info("Generating LLM-enhanced analysis report (this may take a minute)...")
    result = ollama_chat(model, messages, temperature=0.4, num_ctx=16384)

    if "error" in result:
        fail(f"Report generation failed: {result['error']}")
        return "# Analysis Report\n\nGeneration failed. See raw JSONL for data."

    content = result.get("message", {}).get("content", "")
    elapsed = result.get("_elapsed_s", 0)
    ok(f"Report generated ({len(content)} chars, {elapsed:.1f}s)")

    return content


# ── User Logs Parser ──────────────────────────────────────────────────────────

def parse_user_logs(limit_probes=12, turns_of_history=4):
    """
    Parses user logs under knowledge_base/user_logs/ and extracts conversation turns.
    Returns: a list of probe dicts.
    """
    import glob
    import re
    import random

    user_logs_dir = PROJECT_ROOT / "knowledge_base" / "user_logs"
    if not user_logs_dir.exists():
        warn("user_logs directory not found, skipping conversation log replay.")
        return []

    user_dirs = [d for d in user_logs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    probes = []
    msg_start_re = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)')

    for user_dir in user_dirs:
        username = user_dir.name.split("_")[0]
        md_files = sorted(glob.glob(str(user_dir / "*.md")), reverse=True)
        
        user_probes = []
        for fn in md_files:
            if "user_profile.md" in fn:
                continue
            try:
                content = Path(fn).read_text(encoding="utf-8")
            except Exception:
                continue
                
            messages = []
            current_msg = None
            
            for line in content.splitlines():
                m = msg_start_re.match(line)
                if m:
                    if current_msg:
                        messages.append(current_msg)
                    timestamp_str, sender, msg_content = m.groups()
                    role = "assistant" if sender.lower() == "kaia" else "user"
                    current_msg = {
                        "role": role,
                        "sender": sender,
                        "content": msg_content.strip()
                    }
                else:
                    if current_msg:
                        current_msg["content"] += "\n" + line.strip()
                        
            if current_msg:
                messages.append(current_msg)
                
            for i, msg in enumerate(messages):
                if msg["role"] == "user" and msg["content"].strip():
                    prompt_text = msg["content"].strip()
                    if prompt_text.startswith("http") or prompt_text.startswith("https"):
                        continue
                    if len(re.sub(r'[^a-zA-Z0-9\s]', '', prompt_text).strip()) < 8:
                        continue
                        
                    history = []
                    start_idx = max(0, i - turns_of_history)
                    for h_msg in messages[start_idx:i]:
                        h_content = h_msg["content"].strip()
                        h_content = re.sub(r'https?://\S+', '[link]', h_content)
                        history.append({
                            "role": h_msg["role"],
                            "content": h_content
                        })
                    
                    probe_id = f"replay_{username}_{Path(fn).stem}_{i}"
                    user_probes.append({
                        "id": probe_id,
                        "prompt": prompt_text,
                        "history": history,
                        "user": username,
                        "watch_for": [],
                        "hypothesis": f"Replays actual historical message from {username} in {Path(fn).name}"
                    })
            if len(user_probes) >= 5:
                break
        probes.extend(user_probes)

    random.seed(42)
    random.shuffle(probes)
    if len(probes) > limit_probes:
        probes = probes[:limit_probes]
    return probes


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Kaia J-Space Behavioral Probing Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "This tool runs diagnostic probes through Ollama to analyze how\n"
            "Kaia's persona reshapes Gemma 3 12B's response distribution.\n"
            "Must be run while the Kaiacord bot is NOT running."
        ),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model tag (default: {DEFAULT_MODEL})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--categories", nargs="+", default=None,
                        help="Run only specific probe categories (default: all)")
    parser.add_argument("--user", default="ekco",
                        help="Simulated user name (default: ekco)")
    parser.add_argument("--skip-user-logs", action="store_true",
                        help="Skip replaying real user conversation logs")
    parser.add_argument("--only-user-logs", action="store_true",
                        help="Only run real user conversation logs, skip static probe battery")
    parser.add_argument("--limit-user-logs", type=int, default=12,
                        help="Limit the number of user log conversations to replay (default: 12)")
    args = parser.parse_args()

    # Resolve output directory relative to project root
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = output_dir / f"jspace_probe_{timestamp}.jsonl"
    report_path = output_dir / f"jspace_report_{timestamp}.md"

    header("Kaia J-Space Behavioral Probing Toolkit")
    info(f"Model: {args.model}")
    info(f"Output: {output_dir}")
    info(f"User: {args.user}")

    # Pre-flight checks
    if not ollama_is_up():
        fail("Ollama is not running! Start it with: systemctl start ollama")
        sys.exit(1)
    ok("Ollama is responding")

    # Check bot is not running
    running_pids = []
    my_pid = os.getpid()
    try:
        for pid_str in os.listdir('/proc'):
            if pid_str.isdigit() and int(pid_str) != my_pid:
                try:
                    cmdline = open(f'/proc/{pid_str}/cmdline', errors='ignore').read().replace('\x00', ' ')
                    if 'Kaiacord.py' in cmdline:
                        exe_link = os.readlink(f'/proc/{pid_str}/exe')
                        if 'python' in exe_link:
                            running_pids.append(pid_str)
                except Exception:
                    continue
    except Exception:
        pass

    if running_pids:
        fail("Kaiacord.py appears to be running! Stop the bot first to avoid VRAM contention.")
        fail("PIDs found: " + ", ".join(running_pids))
        sys.exit(1)
    ok("Bot is not running (safe to proceed)")

    # Verify persona file exists
    persona_path = PROJECT_ROOT / "knowledge_base" / "kaia_persona.md"
    if not persona_path.exists():
        fail(f"Persona file not found: {persona_path}")
        sys.exit(1)
    ok(f"Persona file loaded ({persona_path.stat().st_size:,} bytes)")

    # Load supplementary files
    for name, path in [
        ("Identity stream", "memory/identity_stream.md"),
        ("Self-model", "memory/kaia_self_model.md"),
        ("Beliefs", "memory/beliefs.json"),
        ("Mood state", "memory/mood_state.json"),
    ]:
        p = PROJECT_ROOT / path
        if p.exists():
            ok(f"{name} loaded ({p.stat().st_size:,} bytes)")
        else:
            warn(f"{name} not found ({path})")

    # ── Parse and Inject User Logs ──────────────────────────────────────────
    if not args.skip_user_logs:
        info("Parsing user conversation logs from knowledge base...")
        replay_probes = parse_user_logs(limit_probes=args.limit_user_logs)
        if replay_probes:
            PROBE_BATTERY["user_logs_replay"] = {
                "description": "Replay of real past conversation turns from user logs",
                "probes": replay_probes
            }
            ok(f"Loaded {len(replay_probes)} conversation turns for replay.")

    # Determine which categories to run
    if args.only_user_logs:
        if "user_logs_replay" not in PROBE_BATTERY:
            fail("Cannot run --only-user-logs because no user logs could be parsed.")
            sys.exit(1)
        categories = ["user_logs_replay"]
    else:
        categories = args.categories or list(PROBE_BATTERY.keys())

    invalid = [c for c in categories if c not in PROBE_BATTERY]
    if invalid:
        fail(f"Unknown probe categories: {invalid}")
        fail(f"Available: {list(PROBE_BATTERY.keys())}")
        sys.exit(1)

    total_probes = sum(len(PROBE_BATTERY[c]["probes"]) for c in categories)
    info(f"Running {total_probes} probes across {len(categories)} categories")
    info(f"Estimated time: ~{total_probes * 40}s ({total_probes} probes x 2 paths x ~20s each)")

    # ── Phase 1: Run Probes ──────────────────────────────────────────────────
    header("Phase 1: Dual-Path Probe Execution")

    all_results = []
    probe_num = 0

    for cat_name in categories:
        cat = PROBE_BATTERY[cat_name]
        print(f"\n{BOLD}{'─' * 60}{NC}", file=sys.stderr)
        print(f"{BOLD}  Category: {cat_name}{NC}", file=sys.stderr)
        print(f"{DIM}  {cat['description']}{NC}", file=sys.stderr)
        print(f"{BOLD}{'─' * 60}{NC}", file=sys.stderr)

        for probe in cat["probes"]:
            probe_num += 1
            prompt_display = probe["prompt"]
            if len(prompt_display) > 80:
                prompt_display = prompt_display[:80] + "..."
            print(f"\n{YELLOW}[{probe_num}/{total_probes}] Probe: {probe['id']}{NC}",
                  file=sys.stderr)
            print(f"{DIM}  \"{prompt_display}\"{NC}", file=sys.stderr)

            result = run_dual_probe(args.model, cat_name, probe, user_name=args.user)
            all_results.append(result)

            # Write to JSONL incrementally
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

    ok(f"\nPhase 1 complete: {len(all_results)} probes written to {jsonl_path}")

    # ── Phase 1.5: Quick Stats ───────────────────────────────────────────────
    header("Quick Stats Summary")

    total_suppressed = sum(len(r["suppressed_tokens"]) for r in all_results)
    total_leaked = sum(len(r["leaked_tokens"]) for r in all_results)
    total_watched = sum(len(r["watch_for"]) for r in all_results)

    print(f"  Total watched tokens across all probes: {total_watched}", file=sys.stderr)
    print(f"  Tokens suppressed by persona:           {GREEN}{total_suppressed}{NC}",
          file=sys.stderr)
    leak_color = RED if total_leaked else GREEN
    print(f"  Tokens leaked through persona:          {leak_color}{total_leaked}{NC}",
          file=sys.stderr)

    suppression_rate = 0.0
    if total_watched > 0:
        suppression_rate = (
            total_suppressed / max(1, total_suppressed + total_leaked)
        ) * 100
        print(f"  Suppression effectiveness:              {suppression_rate:.1f}%",
              file=sys.stderr)

    avg_kaia_time = sum(r["kaia_elapsed_s"] for r in all_results) / max(1, len(all_results))
    avg_bare_time = sum(r["bare_elapsed_s"] for r in all_results) / max(1, len(all_results))
    print(f"\n  Avg response time (Kaia):    {avg_kaia_time:.1f}s", file=sys.stderr)
    print(f"  Avg response time (bare):    {avg_bare_time:.1f}s", file=sys.stderr)
    print(f"  Persona overhead:            {avg_kaia_time - avg_bare_time:+.1f}s",
          file=sys.stderr)

    # ── Phase 2: LLM Analysis ────────────────────────────────────────────────
    report_content = generate_analysis_report(args.model, all_results)

    # Build full report with header
    if total_watched > 0:
        suppression_line = (
            f"**Suppression rate:** {suppression_rate:.1f}% "
            f"({total_suppressed} suppressed / {total_leaked} leaked)\n"
        )
    else:
        suppression_line = "**Suppression rate:** N/A (no watched tokens in this run)\n"

    full_report = (
        f"# Kaia J-Space Behavioral Probe Report\n\n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Model:** {args.model}\n"
        f"**Probes run:** {len(all_results)} across {len(categories)} categories\n"
        f"{suppression_line}"
        f"**Avg persona overhead:** {avg_kaia_time - avg_bare_time:+.1f}s per probe\n\n"
        f"---\n\n"
        f"## Raw Statistics\n\n"
        f"| Category | Probes | Suppressed | Leaked | Avg Kaia (s) | Avg Bare (s) |\n"
        f"|----------|--------|------------|--------|-------------|-------------|\n"
    )

    for cat_name in categories:
        cat_results = [r for r in all_results if r["category"] == cat_name]
        cat_suppressed = sum(len(r["suppressed_tokens"]) for r in cat_results)
        cat_leaked = sum(len(r["leaked_tokens"]) for r in cat_results)
        cat_kaia_avg = sum(r["kaia_elapsed_s"] for r in cat_results) / max(1, len(cat_results))
        cat_bare_avg = sum(r["bare_elapsed_s"] for r in cat_results) / max(1, len(cat_results))
        full_report += (
            f"| {cat_name} | {len(cat_results)} | {cat_suppressed} | {cat_leaked} | "
            f"{cat_kaia_avg:.1f} | {cat_bare_avg:.1f} |\n"
        )

    full_report += f"\n---\n\n## LLM-Enhanced Analysis\n\n{report_content}\n"

    # Append raw probe details
    full_report += "\n---\n\n## Raw Probe Details\n\n"
    for r in all_results:
        kaia_preview = r["kaia_response"][:300]
        if len(r["kaia_response"]) > 300:
            kaia_preview += "..."
        bare_preview = r["bare_response"][:300]
        if len(r["bare_response"]) > 300:
            bare_preview += "..."
        full_report += (
            f"### {r['probe_id']} ({r['category']})\n\n"
            f"**Prompt:** {r['prompt']}\n\n"
            f"**Hypothesis:** {r['hypothesis']}\n\n"
            f"**Kaia Response** ({r['kaia_elapsed_s']:.1f}s, {r['kaia_eval_count']} tokens):\n"
            f"> {kaia_preview}\n\n"
            f"**Bare Response** ({r['bare_elapsed_s']:.1f}s, {r['bare_eval_count']} tokens):\n"
            f"> {bare_preview}\n\n"
            f"**Watch hits (Kaia):** {r['kaia_watch_hits']}\n"
            f"**Watch hits (bare):** {r['bare_watch_hits']}\n"
            f"**Suppressed:** {r['suppressed_tokens']}\n"
            f"**Leaked:** {r['leaked_tokens']}\n\n"
            f"---\n\n"
        )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    ok(f"\nReport written to {report_path}")

    # ── Done ─────────────────────────────────────────────────────────────────
    header("Complete")
    print(f"  {BOLD}Raw data:{NC}  {jsonl_path}", file=sys.stderr)
    print(f"  {BOLD}Report:{NC}    {report_path}", file=sys.stderr)
    total_time = sum(r["kaia_elapsed_s"] + r["bare_elapsed_s"] for r in all_results)
    print(f"  {BOLD}Total time:{NC} {total_time:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
