import re

from fastapi.responses import JSONResponse

from shared.auth import get_session, role_meets_minimum

# BUG FIX (2026-09 audit): this previously enforced a minimum rank on exactly
# one route (/api/export/pdf) -- every other endpoint, including case
# deletion, exclusion/contradiction records, hypothesis resolution and
# collaborator management, required nothing beyond "any authenticated
# session". A constable and a DySP had identical write access to every
# consequential action in the system, which contradicts the rank hierarchy
# this middleware exists to enforce. ROUTE_MIN_ROLE now covers every mutating
# or sensitive route; unlisted (method, path) pairs still default to "any
# authenticated session" for reads and low-stakes actions, which is an
# intentional policy choice, not an oversight -- see
# Docs/audit/2026-09-01_security_audit_and_fixes.md for the full
# route-by-route rationale, and flag any disagreement there for review since
# these are domain/policy calls this patch cannot make alone.

PUBLIC_PATHS = {"/health", "/api/auth/login"}

# {param} matches one path segment (no "/"), so "/api/cases/{id}" matches
# "/api/cases/abc123" but NOT "/api/cases/abc123/sessions" -- unlike a bare
# fnmatch "*", which would swallow the "/" and over-match every nested
# sub-route. Each entry is (HTTP method, path template, minimum role); a
# route not listed here requires only a valid session, at any rank. Ranks:
# dysp > inspector > sub_inspector > asi > head_constable > constable (see
# shared/auth.py ROLE_HIERARCHY).
ROUTE_MIN_ROLE = [
    ("POST", "/api/export/pdf", "sub_inspector"),

    # Case management: deleting a case or adding a collaborator changes who
    # has access to an investigation, so both require rank. Creating a case,
    # reading it, and working its sessions/board/hypotheses stay open to any
    # authenticated officer on the case.
    ("DELETE", "/api/cases/{case_id}", "sub_inspector"),
    ("POST", "/api/cases/{case_id}/collaborators", "sub_inspector"),

    # Negative evidence / exclusions: ruling a suspect out (or reversing
    # that) is exactly the kind of consequential, hard-to-undo action rank
    # exists to gate. Reversing is stricter than creating -- it puts a
    # previously-excluded suspect back in scope.
    ("POST", "/api/investigation/exclude", "asi"),
    ("POST", "/api/investigation/exclude/{exclusion_id}/reverse", "sub_inspector"),
    ("POST", "/api/investigation/contradiction", "asi"),

    # Review queue resolution (proactive alerts -- cold-case matches, ANPR
    # hits) should be signed off by someone with authority to act on it, not
    # just whoever happens to be logged in when the alert fires.
    ("POST", "/api/review-queue/{item_id}/resolve", "asi"),
]


def _compile_route_patterns():
    # Build the regex segment-by-segment (split first, escape/substitute
    # second) rather than escaping the whole template and trying to punch
    # holes back through it -- re.escape() would mangle the "{...}"
    # delimiters themselves, making a post-hoc substitution unreliable. Each
    # "{param}" segment becomes a single-path-segment capture ("[^/]+", so it
    # can't itself contain "/" and jump into a differently-gated sub-route);
    # every other segment is escaped and matched literally.
    compiled = []
    for method, template, role in ROUTE_MIN_ROLE:
        parts = []
        for segment in template.split("/"):
            if segment.startswith("{") and segment.endswith("}"):
                parts.append("[^/]+")
            else:
                parts.append(re.escape(segment))
        regex = "^" + "/".join(parts) + "$"
        compiled.append((method, re.compile(regex), role))
    return compiled


_COMPILED_ROUTES = _compile_route_patterns()


def _match_min_role(method: str, path: str) -> str | None:
    for route_method, pattern, role in _COMPILED_ROUTES:
        if method == route_method and pattern.match(path):
            return role
    return None

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

        min_role = _match_min_role(scope["method"], path)
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
