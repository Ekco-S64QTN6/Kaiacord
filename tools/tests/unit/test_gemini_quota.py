import os
import sys
from google import genai
from dotenv import load_dotenv

def test_gemini():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ Error: GEMINI_API_KEY NOT found in .env")
        return

    print(f"🔍 Testing Gemini API Key: {api_key[:5]}...{api_key[-4:]}")
    client = genai.Client(api_key=api_key)
    
    try:
        print("📡 Sending test request to gemini-2.0-flash...")
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents="Say 'API connection successful' if you can read this."
        )
        print(f"✅ SUCCESS: {response.text.strip()}")
        print("\n💡 Your API key is working perfectly. The 'limit: 0' error in the bot logs might be due to a regional restriction or a brand new Google Cloud project still propagating.")
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ API FAIL: {error_msg}")
        
        if "429" in error_msg:
            print("\n⚠️  QUOTA EXHAUSTED (429)")
            if "limit: 0" in error_msg:
                print("🚨 TRAP: Your project has a LIMIT of 0. This usually means:")
                print("1. Your Google Cloud project is brand new (propagation takes ~1 hour).")
                print("2. You haven't enabled the 'Generative Language API' in your Google Cloud Console.")
                print("3. Your region doesn't support the Free Tier.")
            else:
                print("You reached your requests-per-minute or requests-per-day limit.")
        elif "403" in error_msg:
            print("\n⚠️  PERMISSION DENIED (403)")
            print("Check if the API Key is restricted or if the API is enabled.")
        elif "400" in error_msg:
            print("\n⚠️  BAD REQUEST (400)")
            print("The model or parameters might be incorrect.")

if __name__ == "__main__":
    test_gemini()
