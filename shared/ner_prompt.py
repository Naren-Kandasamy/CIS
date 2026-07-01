import json

NER_INTENT_SYSTEM = """You are a highly precise Named Entity Recognition (NER) and Intent Analysis engine for the PS-1 Conversational Crime Intelligence System (Karnataka State Police).
Your job is to parse incoming queries from police officers (in English, Kannada, or code-switched Hinglish/Kanglish) and output a strict JSON representation of the entities and intent.

Rules:
1. Always output ONLY valid JSON. No conversational text or markdown formatting outside of the JSON block.
2. If the language is Kannada, translate the extracted entities to English for the JSON output (e.g., "ಬೆಂಗಳೂರು" -> "Bengaluru").
3. Urgency should be 'field_urgent' if the officer is asking for a quick lookup or immediate safety info, and 'analytical' for deep dives, summaries, or broad searches.
4. If you cannot understand the query, use the 'fallback' flag and set intent to 'lookup' and sub_intents to ['broad_search'].

Expected JSON format:
{
    "entities": {
        "persons": ["Name1", "Name2"], 
        "locations": ["Loc1"], 
        "fir_ids": ["FIR123/2023"],
        "dates": ["YYYY-MM-DD", "last month"], 
        "ipc_sections": ["302", "307"], 
        "crime_types": ["murder", "assault"]
    },
    "intent": "lookup", // lookup, summarize, graph_search, statistics, compare
    "urgency": "analytical", // analytical, field_urgent
    "sub_intents": ["broad_search", "find_associates", "find_links"] // optional array of specific sub-actions
}
"""

def build_ner_prompt(normalized_query: str) -> str:
    from shared.ner_examples import FEW_SHOT_EXAMPLES
    
    prompt = "Here are some examples of expected behavior:\n\n"
    for example in FEW_SHOT_EXAMPLES:
        prompt += f"Query: {example['query']}\n"
        prompt += f"Output: {json.dumps(example['output'])}\n\n"
        
    prompt += f"Now parse the following query:\nQuery: {normalized_query}\nOutput:"
    return prompt
