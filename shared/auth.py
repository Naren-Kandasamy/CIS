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


def role_meets_minimum(role: str, minimum_role: str) -> bool:
    """True if `role` has at least as much authority as `minimum_role`."""
    if role not in ROLE_RANK or minimum_role not in ROLE_RANK:
        return False
    return ROLE_RANK[role] <= ROLE_RANK[minimum_role]


async def get_user(username: str) -> dict | None:
    doc = await nosql_get(f"user:{username}")
    return json.loads(doc["value"]) if doc else None


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
    return json.loads(doc["value"]) if doc else None
