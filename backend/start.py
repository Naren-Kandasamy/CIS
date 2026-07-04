import os
import subprocess
import sys
import site

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_here)

if __name__ == "__main__":
    # BUG FIX: Catalyst AppSail's Python stack never runs `pip install` for us --
    # its deploy pipeline only auto-installs requirements.txt for Functions, not
    # AppSail (confirmed by reading the CLI's own source: pip-install logic only
    # appears under fn-utils/init/pull for functions, never under deploy/appsail).
    # Installing here, with the same interpreter that will run the app, before
    # importing uvicorn (which would otherwise fail before install ever ran).
    req_path = os.path.join(_here, "requirements.txt")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True)

    # BUG FIX: Catalyst's container reports "Defaulting to user installation
    # because normal site-packages is not writeable" -- pip installs to
    # ~/.local/lib/pythonX.Y/site-packages, but this interpreter doesn't have
    # that directory on sys.path (user-site appears disabled), so everything
    # just installed is still unimportable in this same process without this.
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.insert(0, user_site)

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
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ["X_ZOHO_CATALYST_LISTEN_PORT"]))
