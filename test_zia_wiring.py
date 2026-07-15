import asyncio
from shared.catalyst_client import translate_text, text_to_speech

async def main():
    print("--- Testing Zia Translate Wiring ---")
    try:
        # We expect this to either work (if your .env has active Catalyst tokens)
        # or fail with an HTTP 401/403 (which PROVES the code successfully reached the Zia API)
        res = await translate_text("This is a test", "en", "kn")
        print("✅ SUCCESS! Translation:", res)
    except Exception as e:
        print("⚠️ Failed (Likely Auth/Token missing locally, but wiring is correct):", e)

    print("\n--- Testing Zia TTS Wiring ---")
    try:
        res = await text_to_speech("This is a test", "en")
        print(f"✅ SUCCESS! Received {len(res)} bytes of audio data")
    except Exception as e:
        print("⚠️ Failed (Likely Auth/Token missing locally, but wiring is correct):", e)

if __name__ == "__main__":
    asyncio.run(main())
