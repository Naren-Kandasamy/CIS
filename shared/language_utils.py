import re

VIABLE_LANGUAGES = {"en"}

def detect_language(text: str) -> str | None:
    """
    Deterministic, local, no-LLM-call language detection.
    Returns an ISO 639-1 code (e.g. "en", "kn", "ta") or None if detection
    fails (empty/too-short text).
    Never raises -- ingestion and retrieval callers should not need a
    try/except around this.
    """
    if not text or not text.strip():
        return None
    # Basic unicode heuristic instead of langdetect due to Catalyst install failures
    if re.search(r'[\u0C80-\u0CFF]', text):
        return 'kn'
    if re.search(r'[\u0900-\u097F]', text):
        return 'hi'
    if re.search(r'[\u0B80-\u0BFF]', text):
        return 'ta'
    # Default to English if mostly ASCII
    return 'en'

def is_viable(language_code: str | None) -> bool:
    """
    True if the language is one the pipeline can work with directly
    (English) without a translation hop.
    A None/undetectable language is treated as NOT viable -- safer to
    attempt translation (or flag for review) than to silently assume
    it's fine.
    """
    return language_code in VIABLE_LANGUAGES
