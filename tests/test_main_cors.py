import importlib
import os
import sys


def test_cors_wildcard_origin_raises_at_import():
    # BUG FIX regression coverage: CORS_ALLOWED_ORIGINS="*" combined with
    # allow_credentials=True is an invalid-but-silently-accepted combination
    # in Starlette's CORSMiddleware (it falls back to reflecting any Origin
    # header). backend/main.py now fails loudly at import time instead.
    old_env = os.environ.get("CORS_ALLOWED_ORIGINS")
    old_module = sys.modules.pop("backend.main", None)
    os.environ["CORS_ALLOWED_ORIGINS"] = "*"
    try:
        raised = False
        try:
            importlib.import_module("backend.main")
        except EnvironmentError as e:
            raised = True
            assert "CORS_ALLOWED_ORIGINS must not be" in str(e)
        assert raised, "expected EnvironmentError for wildcard CORS origin"
    finally:
        if old_env is None:
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        else:
            os.environ["CORS_ALLOWED_ORIGINS"] = old_env
        sys.modules.pop("backend.main", None)
        if old_module is not None:
            sys.modules["backend.main"] = old_module
        else:
            # Re-import cleanly with a safe origin so later test modules that
            # do `from backend.main import app` at collection time still work.
            importlib.import_module("backend.main")
