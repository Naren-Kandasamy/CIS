import re
import json
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

MAX_TEXT_QUERY_LEN = 500
MAX_AUDIO_SIZE_BYTES = 5 * 1024 * 1024
MAX_DOC_SIZE_BYTES = 10 * 1024 * 1024

# Denylist for SQL, Cypher, and Prompt Injection
# Highly specific to avoid false positives on natural language words like "match" or "update"
DENYLIST_PATTERNS = [
    # SQL
    r"(?i)\b(SELECT\s+.*?\s+FROM|INSERT\s+INTO|UPDATE\s+.*?\s+SET|DELETE\s+FROM|DROP\s+(TABLE|DATABASE)|ALTER\s+TABLE|TRUNCATE\s+TABLE|UNION\s+SELECT)\b",
    # Cypher
    r"(?i)\b(MATCH\s*\(|MERGE\s*\(|CREATE\s*\(|YIELD\s+.*?\s+RETURN|UNWIND\s+.*?\s+AS)\b",
    r"-\[.*?\]->", # Cypher relationship
    # Prompt injection
    r"(?i)ignore previous instructions",
    r"(?i)system prompt",
    r"(?i)you are a\b",
    r"(?i)disregard previous",
]

class InputValidationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        content_type = headers.get(b"content-type", b"")

        # 1. Size checks via Content-Length (fail fast before reading)
        if content_length:
            try:
                length = int(content_length)
                path = scope.get("path", "")
                if path.endswith("/transcribe") and length > MAX_AUDIO_SIZE_BYTES:
                    return await self._send_error(scope, receive, send, 413, "Audio upload exceeds 5MB limit")
                elif path.endswith("/upload") and length > MAX_DOC_SIZE_BYTES:
                    return await self._send_error(scope, receive, send, 413, "Document upload exceeds 10MB limit")
                elif b"application/json" in content_type and length > 2048:
                    return await self._send_error(scope, receive, send, 413, "Payload too large")
            except ValueError:
                pass

        # 2. Pattern & length checks for text queries
        if scope["method"] in ["POST", "PUT", "PATCH"] and b"application/json" in content_type:
            if scope.get("path", "").endswith("/query"):
                # Read the body
                body = b""
                more_body = True
                while more_body:
                    message = await receive()
                    body += message.get("body", b"")
                    more_body = message.get("more_body", False)

                try:
                    body_json = json.loads(body)
                    query_text = body_json.get("query", "")
                    
                    if not query_text or not str(query_text).strip():
                        return await self._send_error(scope, receive, send, 400, "Query cannot be empty")
                    
                    query_text = str(query_text)
                    if len(query_text) > MAX_TEXT_QUERY_LEN:
                        return await self._send_error(scope, receive, send, 400, "Query exceeds 500 characters limit")
                    
                    for pattern in DENYLIST_PATTERNS:
                        if re.search(pattern, query_text):
                            return await self._send_error(scope, receive, send, 400, "Invalid input pattern detected")
                except json.JSONDecodeError:
                    return await self._send_error(scope, receive, send, 400, "Invalid JSON format")

                # Re-inject the body for downstream
                # Notice we simulate exactly what the application expects: a single message with the full body,
                # since we already consumed it. (In a real scenario, you'd buffer it in chunks if large, but we capped it at 2KB).
                original_receive = receive
                received = False
                async def new_receive():
                    nonlocal received
                    if not received:
                        received = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await original_receive()
                
                receive = new_receive

        await self.app(scope, receive, send)

    async def _send_error(self, scope, receive, send, status_code: int, detail: str):
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)

# Utility for MIME sniffing endpoints to use
def validate_mime_type(file_bytes: bytes, allowed_mimes: list[str]) -> bool:
    """
    Very basic magic number MIME sniffing.
    """
    if not file_bytes:
        return False
        
    signatures = {
        b"\xFF\xD8\xFF": "image/jpeg",
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"%PDF-": "application/pdf",
        b"\x1A\x45\xDF\xA3": "audio/webm",
        b"ID3": "audio/mpeg",
        b"\xFF\xFB": "audio/mpeg",
        b"RIFF": "audio/wav", 
        b"OggS": "audio/ogg"
    }
    
    for sig, mime in signatures.items():
        if file_bytes.startswith(sig):
            if mime in allowed_mimes:
                return True
            # Special case for RIFF/WAV
            if sig == b"RIFF" and len(file_bytes) >= 12 and file_bytes[8:12] == b"WAVE" and "audio/wav" in allowed_mimes:
                 return True

    return False
