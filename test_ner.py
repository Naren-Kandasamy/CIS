import asyncio
from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def main():
    q = "Summarize those cases again into bullet points please."
    res = await extract_ner_and_intent(q)
    print(res)

asyncio.run(main())
