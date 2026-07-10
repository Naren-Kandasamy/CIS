import os
import subprocess
import sys
import site

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_here)

if __name__ == "__main__":
    packages_path = os.path.join(_here, ".packages")
    if os.path.exists(packages_path) and packages_path not in sys.path:
        sys.path.insert(0, packages_path)

    # BUG FIX: main.py imports assume a repo-root perspective (from
    # backend.api.routes import ..., from shared.catalyst_client import ...),
    # matching how this codebase is always run locally, but the deployed
    # AppSail's build_path now uploads the whole repo with this file exec'd
    # directly -- sys.path[0] only has this file's own directory (backend/),
    # not its parent, so "backend.X" and "shared.X" wouldn't resolve without
    # explicitly adding the repo root here.
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.environ["X_ZOHO_CATALYST_LISTEN_PORT"]))
