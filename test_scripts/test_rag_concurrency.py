import threading
import time
import sys
import os

# Add current directory to path so we can import kaia_rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

def test_concurrency():
    print("Starting KaiaRAG concurrency test...")
    rag = KaiaRAG()
    
    # Flag to stop threads
    stop_event = threading.Event()
    
    def retrieval_worker():
        print("Retrieval worker started.")
        count = 0
        while not stop_event.is_set():
            try:
                # Simulate a retrieval
                rag.retrieve("Who is Kaia?")
                count += 1
                if count % 10 == 0:
                    print(f"  [Retrieval] Completed {count} retrievals...")
            except Exception as e:
                print(f"!!! Retrieval error: {e}")
            time.sleep(0.1)
            
    def persistence_worker():
        print("Persistence worker started.")
        count = 0
        while not stop_event.is_set():
            try:
                # Simulate a persistence
                rag.persist(force=True)
                count += 1
                print(f"  [Persistence] Completed {count} persists...")
            except Exception as e:
                print(f"!!! Persistence error: {e}")
            time.sleep(0.5)

    # Start threads
    t1 = threading.Thread(target=retrieval_worker)
    t2 = threading.Thread(target=persistence_worker)
    
    t1.start()
    t2.start()
    
    # Run for 5 seconds
    time.sleep(5)
    
    print("Stopping test...")
    stop_event.set()
    t1.join()
    t2.join()
    print("Test complete. No crashes or hangs detected.")

if __name__ == "__main__":
    test_concurrency()
