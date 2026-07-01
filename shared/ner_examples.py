FEW_SHOT_EXAMPLES = [
    {
        "query": "Find associates of Ravi Kumar in Koramangala",
        "output": {
            "entities": {
                "persons": ["Ravi Kumar"],
                "locations": ["Koramangala"],
                "fir_ids": [],
                "dates": [],
                "ipc_sections": [],
                "crime_types": []
            },
            "intent": "graph_search",
            "urgency": "analytical",
            "sub_intents": ["find_associates"]
        }
    },
    {
        "query": "Show me murder cases from last month in Indiranagar. I need this immediately.",
        "output": {
            "entities": {
                "persons": [],
                "locations": ["Indiranagar"],
                "fir_ids": [],
                "dates": ["last month"],
                "ipc_sections": [],
                "crime_types": ["murder"]
            },
            "intent": "lookup",
            "urgency": "field_urgent",
            "sub_intents": ["broad_search"]
        }
    },
    {
        "query": "ಇಂದಿರಾನಗರದಲ್ಲಿ ಕಳೆದ ತಿಂಗಳು ನಡೆದ ಕೊಲೆ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ", 
        "output": {
            "entities": {
                "persons": [],
                "locations": ["Indiranagar"],
                "fir_ids": [],
                "dates": ["last month"],
                "ipc_sections": [],
                "crime_types": ["murder"]
            },
            "intent": "lookup",
            "urgency": "analytical",
            "sub_intents": ["broad_search"]
        }
    },
    {
        "query": "Summarize FIR 123/2023 from Jayanagar station",
        "output": {
            "entities": {
                "persons": [],
                "locations": ["Jayanagar"],
                "fir_ids": ["123/2023"],
                "dates": [],
                "ipc_sections": [],
                "crime_types": []
            },
            "intent": "summarize",
            "urgency": "analytical",
            "sub_intents": []
        }
    },
    {
        "query": "Give me stats on section 302 cases across Bangalore for 2023",
        "output": {
            "entities": {
                "persons": [],
                "locations": ["Bangalore"],
                "fir_ids": [],
                "dates": ["2023"],
                "ipc_sections": ["302"],
                "crime_types": []
            },
            "intent": "statistics",
            "urgency": "analytical",
            "sub_intents": []
        }
    },
    {
        "query": "Are there any common links between the Majestic theft and the recent robbery in Jayanagar?",
        "output": {
            "entities": {
                "persons": [],
                "locations": ["Majestic", "Jayanagar"],
                "fir_ids": [],
                "dates": ["recent"],
                "ipc_sections": [],
                "crime_types": ["theft", "robbery"]
            },
            "intent": "compare",
            "urgency": "analytical",
            "sub_intents": ["find_links"]
        }
    },
    {
        "query": "ಯಾವುದಾದರೂ section 392 cases ಇದೆಯಾ recent ಆಗಿ? Quick check madi.",
        "output": {
            "entities": {
                "persons": [],
                "locations": [],
                "fir_ids": [],
                "dates": ["recent"],
                "ipc_sections": ["392"],
                "crime_types": []
            },
            "intent": "lookup",
            "urgency": "field_urgent",
            "sub_intents": ["broad_search"]
        }
    },
    {
        "query": "Check criminal history of Syed in Shivajinagar area",
        "output": {
            "entities": {
                "persons": ["Syed"],
                "locations": ["Shivajinagar"],
                "fir_ids": [],
                "dates": [],
                "ipc_sections": [],
                "crime_types": []
            },
            "intent": "lookup",
            "urgency": "analytical",
            "sub_intents": ["background_check"]
        }
    },
    {
        "query": "ರವಿ ಮತ್ತು ಕುಮಾರ್ ನಡುವಿನ ಸಂಬಂಧವೇನು?",
        "output": {
            "entities": {
                "persons": ["Ravi", "Kumar"],
                "locations": [],
                "fir_ids": [],
                "dates": [],
                "ipc_sections": [],
                "crime_types": []
            },
            "intent": "graph_search",
            "urgency": "analytical",
            "sub_intents": ["find_links"]
        }
    },
    {
        "query": "What is the MO for the latest chain snatching incidents?",
        "output": {
            "entities": {
                "persons": [],
                "locations": [],
                "fir_ids": [],
                "dates": ["latest"],
                "ipc_sections": [],
                "crime_types": ["chain snatching"]
            },
            "intent": "lookup",
            "urgency": "analytical",
            "sub_intents": ["mo_search"]
        }
    }
]
