import asyncio
from typing import Tuple, Optional
from rapidfuzz import process, fuzz
from shared.catalyst_client import ztsql_query

# In-memory cache for lookup tables to avoid repeated DB calls in the 15-min function lifecycle
_CRIME_SUB_HEADS_CACHE: dict = {}
_SECTIONS_CACHE: dict = {}
_CACHE_LOADED = False
# BUG FIX: asyncio.Lock prevents a race condition where two concurrent invocations
# both find _CACHE_LOADED=False and both fire the DB load, doubling the I/O and
# potentially interleaving partial state into the caches.
_CACHE_LOCK = asyncio.Lock()

async def _load_caches_if_needed():
    global _CACHE_LOADED, _CRIME_SUB_HEADS_CACHE, _SECTIONS_CACHE
    if _CACHE_LOADED:
        return
    async with _CACHE_LOCK:
        # Double-checked locking: re-check after acquiring lock
        if _CACHE_LOADED:
            return
        
        sub_heads_ok = False
        sections_ok = False

        # Load crime_sub_heads
        try:
            sub_heads = await ztsql_query("SELECT crime_sub_head_id, crime_sub_head_name FROM crime_sub_heads")
            for row in sub_heads:
                _CRIME_SUB_HEADS_CACHE[row["crime_sub_head_id"]] = row["crime_sub_head_name"]
            sub_heads_ok = True
        except Exception as e:
            print(f"Warning: Failed to load crime_sub_heads cache: {e}")

        # Load sections
        try:
            sections = await ztsql_query("SELECT section_code, act_code FROM sections")
            for row in sections:
                key = (row["act_code"], row["section_code"])
                _SECTIONS_CACHE[key] = row["section_code"]
            sections_ok = True
        except Exception as e:
            print(f"Warning: Failed to load sections cache: {e}")

        # BUG FIX: only mark cache loaded if at least one table loaded successfully.
        # Previously _CACHE_LOADED was set unconditionally, so a transient DB failure
        # at cold-start would permanently disable both lookups for the function's lifetime.
        if sub_heads_ok or sections_ok:
            _CACHE_LOADED = True

async def get_crime_sub_head_name(crime_sub_head_id: str) -> Optional[str]:
    """Reverse lookup: resolved crime_sub_head_id -> its display name, reusing
    the same cache resolve_crime_sub_head() loads."""
    await _load_caches_if_needed()
    return _CRIME_SUB_HEADS_CACHE.get(crime_sub_head_id)

async def resolve_crime_sub_head(crime_type_text: str) -> Optional[str]:
    """
    "murder" -> CrimeSubHeadID, via fuzzy match against crime_sub_heads.crime_sub_head_name.
    Returns None if no confident match -- caller decides whether to fall back
    to free-text narrative search (RAG) instead of a structured filter.
    """
    await _load_caches_if_needed()
    if not _CRIME_SUB_HEADS_CACHE:
        return None
        
    # RapidFuzz process.extractOne with dict can have unexpected key type across versions
    # Safer to extract from values list and map back by index
    names = list(_CRIME_SUB_HEADS_CACHE.values())
    ids = list(_CRIME_SUB_HEADS_CACHE.keys())
    result = process.extractOne(
        crime_type_text, 
        names, 
        scorer=fuzz.WRatio
    )
    
    if result:
        match_string, score, match_index = result
        if score >= 80.0:  # 80% confidence threshold
            return ids[match_index]
            
    return None

async def resolve_act_section(ipc_section_text: str) -> Optional[Tuple[str, str]]:
    """
    "302" -> ("IPC", "302"), via lookup against sections.section_code,
    defaulting to act_code="IPC" when the officer doesn't name the act
    explicitly.
    """
    await _load_caches_if_needed()
    if not _SECTIONS_CACHE:
        # Fallback if DB not ready: assume IPC and the text is the exact section code
        return ("IPC", str(ipc_section_text).strip())
        
    text_upper = str(ipc_section_text).strip().upper()
    
    act_guess = "IPC"
    section_guess = text_upper
    
    # Try to parse act vs section if space provided, e.g., "NDPS 20"
    parts = text_upper.split(maxsplit=1)
    if len(parts) == 2:
        potential_act = parts[0]
        # Check if potential_act is a known act code in our cache
        known_acts = {act for act, sec in _SECTIONS_CACHE.keys()}
        if potential_act in known_acts:
            act_guess = potential_act
            section_guess = parts[1]
    else:
        # If text is just "IPC302" or similar
        if text_upper.startswith("IPC"):
            section_guess = text_upper.replace("IPC", "").strip()
            
    # Filter choices to only those matching the guessed act
    choices = {k: v for k, v in _SECTIONS_CACHE.items() if k[0] == act_guess}
    
    if not choices:
        return (act_guess, section_guess) # optimistic fallback
        
    names = list(choices.values())
    ids = list(choices.keys())
    result = process.extractOne(
        section_guess,
        names,
        scorer=fuzz.WRatio
    )
    
    if result:
        match_string, score, match_index = result
        if score >= 85.0:
            return ids[match_index] # This is the (act_code, section_code) tuple
            
    # If no confident match, return our best structural guess
    return (act_guess, section_guess)
