from fastapi.responses import JSONResponse

from shared.auth import get_session, role_meets_minimum

# BUG FIX: this was previously a complete pass-through no-op -- every request
# reached every route with zero access control. Now validates a Bearer
# session token (from /api/auth/login) against the real Catalyst NoSQL
# session store, and enforces a minimum KSP rank per route where specified.

PUBLIC_PATHS = {"/health", "/api/auth/login"}

# Minimum rank required for a route; routes not listed here just require any
# authenticated session. Ranks: dysp > inspector > sub_inspector > asi >
# head_constable > constable (see shared/auth.py ROLE_HIERARCHY).
ROUTE_MIN_ROLE = {
    "/api/export/pdf": "sub_inspector",
}

# BUG FIX (authorization): resolve_review_item let ANY authenticated officer,
# of any rank, permanently mark a cold-case-match / contradiction /
# ANPR-wanted-hit / interstate-handoff alert as "reviewed" or "dismissed".
# These review-queue items are system-wide, not scoped to any case's
# collaborator list (see shared/review_queue_engine.py -- by design, so any
# officer can see cross-jurisdiction alerts), which meant a constable could
# silently dismiss an alert a DySP was relying on, with no rank check at all.
# ROUTE_MIN_ROLE above only supports exact-path matches (fine for the static
# /api/export/pdf route), but this route has a dynamic {item_id} segment, so
# it needs its own prefix/suffix match instead of a dict lookup.
def _is_review_queue_resolve(path: str) -> bool:
    return path.startswith("/api/review-queue/") and path.endswith("/resolve")

# (matcher, minimum_role) pairs for routes whose path isn't a fixed string.
# Checked in order, after the exact-match ROUTE_MIN_ROLE lookup misses.
DYNAMIC_ROUTE_MIN_ROLE = [
    (_is_review_queue_resolve, "asi"),
]

class RBACMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in PUBLIC_PATHS or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        # BUG FIX: plain .decode() defaults to strict UTF-8 decoding, which
        # raises an unhandled UnicodeDecodeError on a malformed/non-UTF8
        # Authorization header byte sequence (HTTP header values are
        # ISO-8859-1 by spec -- a client can send arbitrary bytes) instead of
        # the clean 401 every other invalid-token shape gets. errors="replace"
        # degrades a malformed header to a token that simply won't match any
        # real session, following the normal "missing/invalid" path below.
        auth_header = headers.get(b"authorization", b"").decode(errors="replace")
        token = auth_header[len("Bearer "):] if auth_header.startswith("Bearer ") else None

        if not token:
            return await self._send_error(scope, receive, send, 401, "Missing or invalid Authorization header")

        session = await get_session(token)
        if not session:
            return await self._send_error(scope, receive, send, 401, "Session expired or invalid -- please log in again")

        min_role = ROUTE_MIN_ROLE.get(path)
        if min_role is None:
            for matcher, role in DYNAMIC_ROUTE_MIN_ROLE:
                if matcher(path):
                    min_role = role
                    break

        if min_role and not role_meets_minimum(session["role"], min_role):
            return await self._send_error(scope, receive, send, 403, "Insufficient rank for this action")

        # BUG FIX: downstream routes (case/session ownership checks) need to
        # know *who* is making the request. request.state (Starlette) reads
        # from scope["state"], which this middleware never populated -- every
        # route re-deriving identity had no session-backed source of truth.
        scope.setdefault("state", {})
        scope["state"]["username"] = session["username"]
        scope["state"]["role"] = session["role"]

        await self.app(scope, receive, send)

    async def _send_error(self, scope, receive, send, status_code: int, detail: str):
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)
