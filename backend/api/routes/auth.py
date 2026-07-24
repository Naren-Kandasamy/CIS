from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.auth import authenticate, create_session, invalidate_session
from shared.catalyst_client import nosql_get, nosql_set

router = APIRouter()

# BUG FIX: /api/auth/login is a PUBLIC_PATH (exempt from RBACMiddleware, see
# api/middleware/rbac.py) and had no rate limiting, lockout, or backoff
# anywhere in the request path -- an attacker with network access could throw
# an unbounded stream of password guesses at a fixed username with no
# defensive signal raised. Tracks consecutive failures per-username in the
# same NoSQL store job status/sessions already use, under a
# "loginfail:{username}" key with a TTL, so a lockout self-expires with no
# separate cleanup job needed.
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60  # 15 minutes

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    # BUG FIX: reject once this username has too many recent consecutive
    # failures, before spending a password check on it. The counter is keyed
    # off the submitted username regardless of whether that account actually
    # exists, so this adds no extra timing/existence signal beyond what
    # authenticate()'s constant-time check below already produces.
    fail_key = f"loginfail:{request.username}"
    fail_doc = await nosql_get(fail_key)
    fail_count = int(fail_doc["value"]) if fail_doc else 0
    if fail_count >= MAX_FAILED_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )

    # authenticate() always pays the same ~100k-iteration PBKDF2 cost whether
    # or not the username exists -- see shared/auth.py for why.
    user = await authenticate(request.username, request.password)
    if not user:
        await nosql_set(fail_key, str(fail_count + 1), ttl=LOGIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if fail_count:
        await nosql_set(fail_key, "0", ttl=1)
    token = await create_session(user["username"], user["role"])
    return {
        "token": token,
        "username": user["username"],
        "role": user["role"],
        "display_name": user.get("display_name", user["username"]),
    }


@router.post("/api/auth/logout")
async def logout(request: Request):
    # BUG FIX: there was previously no way to end a session before its 8h
    # TTL -- a leaked/stolen Bearer token (shared kiosk left logged in, token
    # visible in a proxy log) stayed fully valid for up to a full shift with
    # no way to cut it off. This route requires the same valid Bearer session
    # RBACMiddleware already enforces on every non-public path; it just needs
    # the raw token (not exposed on request.state) to revoke it.
    auth_header = request.headers.get("authorization", "")
    token = auth_header[len("Bearer "):] if auth_header.startswith("Bearer ") else None
    if token:
        await invalidate_session(token)
    return {"status": "logged_out"}
