import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add parent directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from shared.language_utils import detect_language, is_viable
from pipeline_function.pipeline.langgraph_router import should_translate_evidence, AgentState
from pipeline_function.pipeline.evidence import EvidenceObject, EvidenceItem

class TestLanguageUtils(unittest.TestCase):
    def test_detect_language_english(self):
        text = "This is a completely normal english sentence regarding a crime."
        lang = detect_language(text)
        self.assertEqual(lang, "en")
        self.assertTrue(is_viable(lang))

    def test_detect_language_kannada(self):
        # "This is a completely normal sentence" in Kannada (approximate)
        text = "ಇದು ಸಂಪೂರ್ಣವಾಗಿ ಸಾಮಾನ್ಯ ವಾಕ್ಯವಾಗಿದೆ"
        lang = detect_language(text)
        self.assertEqual(lang, "kn")
        self.assertFalse(is_viable(lang))

    def test_detect_language_hindi(self):
        text = "यह एक पूरी तरह से सामान्य वाक्य है"
        lang = detect_language(text)
        self.assertEqual(lang, "hi")
        self.assertFalse(is_viable(lang))

class TestLangGraphRouter(unittest.TestCase):
    def test_should_translate_evidence_viable(self):
        item = EvidenceItem(
            fir_id="123",
            sources=["test"],
            relevance_score=0.9,
            convergent=True,
            evidence_path="direct",
            similarity_reason="test",
            metadata={
                "narrative_language": "en",
                "narrative": "English text",
                "mo_descriptor_language": "en",
                "mo_descriptor": "English text"
            }
        )
        evidence = EvidenceObject(query="", session_id="", urgency="", intent="", entities={}, items=[item])
        state = {"evidence": evidence}
        
        next_node = should_translate_evidence(state)
        self.assertEqual(next_node, "confidence_scoring")

    def test_should_translate_evidence_non_viable_narrative(self):
        item = EvidenceItem(
            fir_id="123",
            sources=["test"],
            relevance_score=0.9,
            convergent=True,
            evidence_path="direct",
            similarity_reason="test",
            metadata={
                "narrative_language": "kn",
                "narrative": "Kannada text",
                "mo_descriptor_language": "en",
                "mo_descriptor": "English text"
            }
        )
        evidence = EvidenceObject(query="", session_id="", urgency="", intent="", entities={}, items=[item])
        state = {"evidence": evidence}
        
        next_node = should_translate_evidence(state)
        self.assertEqual(next_node, "translate_evidence_node")

    def test_should_translate_evidence_untagged_non_viable(self):
        # Missing narrative_language, but text is Kannada
        item = EvidenceItem(
            fir_id="123",
            sources=["test"],
            relevance_score=0.9,
            convergent=True,
            evidence_path="direct",
            similarity_reason="test",
            metadata={
                "narrative": "ಇದು ಸಂಪೂರ್ಣವಾಗಿ ಸಾಮಾನ್ಯ ವಾಕ್ಯವಾಗಿದೆ",
                "mo_descriptor": "English text"
            }
        )
        evidence = EvidenceObject(query="", session_id="", urgency="", intent="", entities={}, items=[item])
        state = {"evidence": evidence}
        
        next_node = should_translate_evidence(state)
        self.assertEqual(next_node, "translate_evidence_node")
        self.assertEqual(item.metadata["narrative_language"], "kn")

if __name__ == '__main__':
    unittest.main()
