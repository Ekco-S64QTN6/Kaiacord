import ollama
import time

def clear_all():
    print("Listing models in ps...")
    ps = ollama.ps()
    for m in ps.models:
        print(f"Unloading {m.model}...")
        ollama.generate(model=m.model, keep_alive=0)
    
    print("Waiting 5s for cleanup...")
    time.sleep(5)
    
    ps = ollama.ps()
    if not ps.models:
        print("Success: All models unloaded.")
    else:
        for m in ps.models:
            print(f"Still loaded: {m.model} ({m.processor})")

if __name__ == "__main__":
    clear_all()
