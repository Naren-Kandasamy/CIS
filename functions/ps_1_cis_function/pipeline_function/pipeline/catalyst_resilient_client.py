import asyncio, random
import httpx
from shared.catalyst_client import llm_complete as _raw_llm_complete

MAX_RETRIES = 3
BASE_DELAY = 1.0

class RateLimitError(Exception): pass
class RateLimitExhaustedError(Exception): pass

async def llm_complete_resilient(prompt: str, system: str, **kwargs) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return await _raw_llm_complete(prompt, system, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                last_error = RateLimitError(str(e))
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)
                    continue
            else:
                raise  # fail fast on 401, 500, etc.
        except httpx.RequestError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
        # BUG FIX: KeyError/IndexError (e.g. resp["choices"][0][...] when the
        # gateway returns {"choices": []} on a moderation block) and
        # json.JSONDecodeError (a ValueError subclass, from r.json() on a
        # non-JSON proxy error page) are deterministic response-parsing
        # failures, not transient rate-limiting. The bare `except Exception`
        # below used to swallow these, retry 3x for nothing, and report them
        # as RateLimitExhaustedError -- hiding the real cause and masquerading
        # a schema/moderation issue as rate limiting indefinitely. Fail fast
        # and let the real exception surface instead.
        except (KeyError, IndexError, ValueError) as e:
            print(f"[LLM Core Error] Non-retryable response error ({type(e).__name__}): {repr(e)}")
            raise
        except Exception as e:
             # Just in case mock or other failure throws non-httpx
             last_error = e
             if attempt < MAX_RETRIES - 1:
                 delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                 await asyncio.sleep(delay)
                 continue

    print(f"[LLM Core Error] Retries exhausted. Last error was: {repr(last_error)}")
    raise RateLimitExhaustedError(
        f"Catalyst LLM rate limited/failed after {MAX_RETRIES} attempts"
    ) from last_error
