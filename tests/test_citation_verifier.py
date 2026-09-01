from pipeline_function.pipeline.synthesis.citation_verifier import extract_cited_fir_ids, verify_citations


def test_extract_cited_fir_ids_basic():
    text = "Suspect linked to prior offense [FIR: 2024-KA-001]. Also see [FIR: 2024-KA-002]."
    assert extract_cited_fir_ids(text) == ["2024-KA-001", "2024-KA-002"]


def test_extract_cited_fir_ids_deduplicates_and_preserves_order():
    text = "[FIR: A] then again [FIR: B] then repeats [FIR: A]"
    assert extract_cited_fir_ids(text) == ["A", "B"]


def test_extract_cited_fir_ids_none_when_no_citations():
    assert extract_cited_fir_ids("No citations here at all.") == []


def test_extract_cited_fir_ids_handles_empty_string():
    assert extract_cited_fir_ids("") == []
    assert extract_cited_fir_ids(None) == []


def test_verify_citations_all_verified():
    evidence = [{"fir_id": "2024-KA-001"}, {"fir_id": "2024-KA-002"}]
    text = "Pattern found across [FIR: 2024-KA-001] and [FIR: 2024-KA-002]."

    result = verify_citations(text, evidence)

    assert result["cited"] == ["2024-KA-001", "2024-KA-002"]
    assert result["verified"] == ["2024-KA-001", "2024-KA-002"]
    assert result["unverified"] == []


def test_verify_citations_flags_fabricated_id():
    # BUG FIX (2026-09 audit) regression coverage: this is the exact failure
    # mode this module exists to catch -- a citation to an ID that was never
    # part of the evidence handed to the LLM, whether from ordinary
    # hallucination or injected instructions in untrusted evidence text.
    evidence = [{"fir_id": "2024-KA-001"}]
    text = "Strong match with a prior case [FIR: 2024-KA-999]."

    result = verify_citations(text, evidence)

    assert result["cited"] == ["2024-KA-999"]
    assert result["verified"] == []
    assert result["unverified"] == ["2024-KA-999"]


def test_verify_citations_mixed_verified_and_unverified():
    evidence = [{"fir_id": "2024-KA-001"}]
    text = "See [FIR: 2024-KA-001] and also the fabricated [FIR: 2024-KA-404]."

    result = verify_citations(text, evidence)

    assert result["verified"] == ["2024-KA-001"]
    assert result["unverified"] == ["2024-KA-404"]


def test_verify_citations_excluded_item_still_counts_as_verified():
    # An excluded/ruled-out evidence item is still a real, retrieved item --
    # citing it (e.g. "considered but ruled out") is a legitimate sourced
    # claim, not a fabrication. Only IDs absent from evidence altogether are
    # "unverified".
    evidence = [{"fir_id": "2024-KA-001", "excluded": True, "exclusion_reason": "Confirmed alibi"}]
    text = "This suspect was considered but ruled out [FIR: 2024-KA-001]."

    result = verify_citations(text, evidence)

    assert result["unverified"] == []
    assert result["verified"] == ["2024-KA-001"]


def test_verify_citations_matches_int_fir_ids_as_strings():
    # evidence.metadata FIR IDs may come through as ints from some sources --
    # comparison must not silently fail on a type mismatch.
    evidence = [{"fir_id": 12345}]
    text = "Match found [FIR: 12345]."

    result = verify_citations(text, evidence)

    assert result["verified"] == ["12345"]


def test_verify_citations_no_citations_in_response():
    result = verify_citations("General analysis with no specific citations.", [{"fir_id": "X"}])
    assert result == {"cited": [], "verified": [], "unverified": []}
