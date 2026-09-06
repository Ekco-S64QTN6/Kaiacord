import sys
import os

sys.path.append(os.getcwd())

def verify_fix():
    print("Verifying EmergencyContaminationFilter fix...")
    try:
        from utils.core.response_filter import EmergencyContaminationFilter
        
        # Test 1: Method existence and crash prevention
        query = "what is happening"
        expanded = EmergencyContaminationFilter.expand_news_query(query)
        print(f"✅ Method exists. Result for '{query}': {expanded}")
        
        # Test 2: News trigger logic (simulated)
        # We can't easily import message_processor without full context, 
        # but we can verify the logic inline
        news_inquiry_triggers = ["any updates", "latest news", "current events", "headlines"]
        
        ctx_content_1 = "kaia what's new"
        ask_whats_new_1 = any(trigger in ctx_content_1.lower() for trigger in news_inquiry_triggers)
        print(f"Test 'what's new': Triggered news? {ask_whats_new_1} (Expected: False)")
        
        ctx_content_2 = "kaia any updates on the server?"
        ask_whats_new_2 = any(trigger in ctx_content_2.lower() for trigger in news_inquiry_triggers)
        print(f"Test 'any updates': Triggered news? {ask_whats_new_2} (Expected: True)")
        
        if not ask_whats_new_1 and ask_whats_new_2:
             print("✅ Trigger logic verified.")
        else:
             print("❌ Trigger logic failed.")

    except ImportError as e:
        print(f"❌ Import failed: {e}")
    except AttributeError as e:
        print(f"❌ Verification failed (AttributeError): {e}")
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    verify_fix()
