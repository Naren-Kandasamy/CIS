import asyncio
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import translate_text, text_to_speech

async def main():
    print("--- Testing Zia Translate Wiring (LIVE) ---")
    try:
        res = await translate_text("This is a test of the Zia models.", "en", "kn")
        print("✅ SUCCESS! Translation:", res)
    except Exception as e:
        print("⚠️ Failed:", e)

    print("\n--- Testing Zia TTS Wiring (LIVE) ---")
    try:
        res = await text_to_speech("Testing voice output.", "en")
        print(f"✅ SUCCESS! Received {len(res)} bytes of audio data")
    except Exception as e:
        print("⚠️ Failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
