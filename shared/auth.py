"""
Minimal real authentication + RBAC for PS-1 CIS.

Rank hierarchy matches the "DYSP down to Constable" note already present in
rbac.py's original stub comment and Agents.md's RBAC reference (Architecture
Section 23). Roles are ordered highest-authority-first; a lower ROLE_RANK
index means more authority.

Credentials and sessions are stored in the same real Catalyst NoSQL table
(AppKeyValueStore) job status and history already use, under "user:" and
"session:" key prefixes -- avoids needing a second NoSQL table created in
the console.
"""
import hashlib
import hmac
import json
import secrets
import time

from shared.catalyst_client import nosql_get, nosql_set

ROLE_HIERARCHY = ["dysp", "inspector", "sub_inspector", "asi", "head_constable", "constable"]
ROLE_RANK = {role: i for i, role in enumerate(ROLE_HIERARCHY)}

SESSION_TTL_SECONDS = 8 * 60 * 60  # one shift


def _hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except Exception:
        return False


# BUG FIX: fixed dummy hash so authenticate() below always pays the same
# ~100k-iteration PBKDF2 cost whether or not the username exists. Generated
# once per process from an arbitrary fixed password -- it never needs to
# match anything, it only needs to be a well-formed "salt$digest" hash for
# verify_password() to chew on.
_DUMMY_PASSWORD_HASH = _hash_password("no-such-user-dummy-password")


def role_meets_minimum(role: str, minimum_role: str) -> bool:
    """True if `role` has at least as much authority as `minimum_role`."""
    if role not in ROLE_RANK or minimum_role not in ROLE_RANK:
        return False
    return ROLE_RANK[role] <= ROLE_RANK[minimum_role]


async def get_user(username: str) -> dict | None:
    doc = await nosql_get(f"user:{username}")
    return json.loads(doc["value"]) if doc else None


# BUG FIX: routes/auth.py previously did `user = await get_user(username);
# if not user or not verify_password(...)`. Python's `or` short-circuits, so
# a nonexistent username returned after a bare NoSQL lookup while a real
# username always paid the ~100k-iteration PBKDF2 cost -- the timing
# difference let an attacker enumerate valid usernames from the login
# endpoint's response latency alone. This single entry point always runs a
# full verify_password() comparison (against a fixed dummy hash when the
# user doesn't exist) before returning success/failure, so both cases cost
# the same.
async def authenticate(username: str, password: str) -> dict | None:
    """Constant-time login check. Returns the user record on success, else None."""
    user = await get_user(username)
    stored_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, stored_hash)
    if not user or not password_ok:
        return None
    return user


async def create_user(username: str, password: str, role: str, display_name: str = "") -> None:
    if role not in ROLE_RANK:
        raise ValueError(f"Unknown role: {role!r}. Must be one of {ROLE_HIERARCHY}")
    user = {
        "username": username,
        "password_hash": _hash_password(password),
        "role": role,
        "display_name": display_name or username,
    }
    await nosql_set(f"user:{username}", json.dumps(user))


async def create_session(username: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    session = {"username": username, "role": role, "created_at": time.time()}
    await nosql_set(f"session:{token}", json.dumps(session), ttl=SESSION_TTL_SECONDS)
    return token


async def get_session(token: str) -> dict | None:
    doc = await nosql_get(f"session:{token}")
    if not doc:
        return None
    session = json.loads(doc["value"])
    # BUG FIX: treat a revoked sentinel (written by invalidate_session below)
    # or any record missing the fields a real session always has as "no
    # session" -- otherwise a logged-out/force-expired token would keep
    # authenticating until nosql eventually purged the record.
    if session.get("revoked") or "username" not in session or "role" not in session:
        return None
    return session


# BUG FIX: there was no way to end a session before its 8h TTL -- a leaked or
# stolen Bearer token (shared kiosk not logged out, token visible in a proxy
# log, stolen laptop) stayed fully valid for up to a full shift with no code
# path to cut it off early. nosql_set is an upsert with no real delete
# primitive, so this overwrites the session record with a short-TTL revoked
# sentinel; get_session() above then treats that as "no session" immediately,
# and the record itself expires from the store a second later regardless.
async def invalidate_session(token: str) -> None:
    """Revoke a session immediately (logout, or an admin cutting off a leaked token)."""
    await nosql_set(f"session:{token}", json.dumps({"revoked": True}), ttl=1)
