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

# BUG FIX (2026-09 audit): the per-username lockout above stops an attacker
# hammering one known/guessed username, but does nothing against a
# credential-spray attack -- one source trying many usernames a few times
# each, staying under each individual username's threshold. Track failures
# per source IP too, with a higher threshold (spraying many real usernames a
# couple of times each is normal-ish traffic for a large department; 20
# failures from one address in 15 minutes is not).
MAX_FAILED_LOGIN_ATTEMPTS_PER_IP = 20
LOGIN_LOCKOUT_SECONDS_PER_IP = 15 * 60  # 15 minutes


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


def _client_ip(request: Request) -> str:
    # BUG FIX: request.client.host on Catalyst AppSail is the platform
    # gateway's own address, not the officer's -- every request looks like it
    # comes from the same source, making the per-IP counter useless (one
    # failed login anywhere locks out the whole department, or nothing ever
    # locks out). AppSail's ingress sets X-Forwarded-For like any standard
    # reverse proxy; take the left-most (original client) entry. Falls back
    # to request.client.host for local dev, where there's no gateway in front
    # of uvicorn and the header won't be present.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/api/auth/login")
async def login(login_request: LoginRequest, request: Request):
    ip = _client_ip(request)
    ip_fail_key = f"loginfail_ip:{ip}"
    ip_fail_doc = await nosql_get(ip_fail_key)
    ip_fail_count = int(ip_fail_doc["value"]) if ip_fail_doc else 0
    if ip_fail_count >= MAX_FAILED_LOGIN_ATTEMPTS_PER_IP:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts from this network. Try again later.",
        )

    # BUG FIX: reject once this username has too many recent consecutive
    # failures, before spending a password check on it. The counter is keyed
    # off the submitted username regardless of whether that account actually
    # exists, so this adds no extra timing/existence signal beyond what
    # authenticate()'s constant-time check below already produces.
    fail_key = f"loginfail:{login_request.username}"
    fail_doc = await nosql_get(fail_key)
    fail_count = int(fail_doc["value"]) if fail_doc else 0
    if fail_count >= MAX_FAILED_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )

    # authenticate() always pays the same ~100k-iteration PBKDF2 cost whether
    # or not the username exists -- see shared/auth.py for why.
    user = await authenticate(login_request.username, login_request.password)
    if not user:
        await nosql_set(fail_key, str(fail_count + 1), ttl=LOGIN_LOCKOUT_SECONDS)
        await nosql_set(ip_fail_key, str(ip_fail_count + 1), ttl=LOGIN_LOCKOUT_SECONDS_PER_IP)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if fail_count:
        await nosql_set(fail_key, "0", ttl=1)
    if ip_fail_count:
        await nosql_set(ip_fail_key, "0", ttl=1)
    token = await create_session(user["username"], user["role"], user.get("home_district"))
    return {
        "token": token,
        "username": user["username"],
        "role": user["role"],
        "display_name": user.get("display_name", user["username"]),
        "home_district": user.get("home_district"),
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
