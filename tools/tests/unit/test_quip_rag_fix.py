
import sys
import os

# Create a mock for the log_success function which might not be imported correctly in this stand-alone script
def log_success(msg):
    print(f"SUCCESS: {msg}")

def test_rag_processing():
    # Mock RAG results as dictionaries (the format that was causing the error)
    rag_results = [
        {"content": "This is a test snippet 1.", "metadata": {"source": "test"}},
        {"content": "This is a test snippet 2.", "metadata": {"source": "test"}}
    ]
    
    system_prompt = "Persona instructions..."
    rag_block = "\n\n### RELEVANT KNOWLEDGE & MEMORIES\n"
    
    try:
        for node in rag_results:
            # Replicating the logic from the fix
            if isinstance(node, dict):
                content = node.get('content', '')
            elif hasattr(node, 'node'):
                content = node.node.get_content()
            else:
                content = node.get_content()
            
            if content:
                rag_block += f"- {content[:400].replace(chr(10), ' ')}...\n"
        
        system_prompt += rag_block
        log_success(f"Successfully processed RAG results.")
        print("Resulting RAG block:")
        print(rag_block)
        
        # Check if snippets are correctly injected
        if "test snippet 1" in rag_block and "test snippet 2" in rag_block:
            print("✅ PASS: RAG snippets correctly injected.")
        else:
            print("❌ FAIL: RAG snippets missing.")
            
    except Exception as e:
        print(f"❌ FAIL: Caught exception: {e}")

if __name__ == "__main__":
    test_rag_processing()
