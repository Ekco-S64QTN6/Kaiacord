import time
import re
import hashlib
import os
import json
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

def bench_regex():
    print("\n--- Regex Performance ---")
    patterns = [
        r"^\s*(<@!?\d+>\s*)?(kaia|hey kaia|hi kaia|hello kaia)[!?.,]*\s*$",
        r"^\s*(kaia\s+)?(status|stats|ping|uptime|clear|reset|quip)\b",
        r"\b(error|bug|fail|crash|exception|traceback|fix|broken|dogshit)\b"
    ]
    query = "hey kaia, why is the system broken and crashing? check logs"
    
    # Uncompiled
    start = time.perf_counter()
    for _ in range(10000):
        for p in patterns:
            re.search(p, query, re.IGNORECASE)
    uncompiled_dur = time.perf_counter() - start
    print(f"Uncompiled: {uncompiled_dur:.6f}s")
    
    # Precompiled
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    start = time.perf_counter()
    for _ in range(10000):
        for cp in compiled:
            cp.search(query)
    compiled_dur = time.perf_counter() - start
    print(f"Precompiled: {compiled_dur:.6f}s")
    print(f"Gain: {uncompiled_dur/compiled_dur:.2f}x faster")

def bench_string_concat():
    print("\n--- String Concatenation vs Join ---")
    lines = ["This is line number " + str(i) for i in range(1000)]
    
    # Concat (+=)
    start = time.perf_counter()
    for _ in range(100):
        s = ""
        for l in lines:
            s += l + "\n"
    concat_dur = time.perf_counter() - start
    print(f"Concat (+=): {concat_dur:.6f}s")
    
    # Join
    start = time.perf_counter()
    for _ in range(100):
        s = "\n".join(lines)
    join_dur = time.perf_counter() - start
    print(f"Join: {join_dur:.6f}s")
    print(f"Gain: {concat_dur/join_dur:.2f}x faster")

def verify_state_structure():
    print("\n--- State Structure Verification ---")
    profiles_dir = "./memory/state/profiles"
    if os.path.exists(profiles_dir):
        files = os.listdir(profiles_dir)
        print(f"Found {len(files)} files in {profiles_dir}")
        if files:
            print(f"Example profile: {files[0]}")
    else:
        print(f"Profiles directory {profiles_dir} NOT FOUND (Expected if no save yet)")

if __name__ == "__main__":
    bench_regex()
    bench_string_concat()
    verify_state_structure()
