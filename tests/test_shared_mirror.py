import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_functions_bundle_mirror_is_in_sync():
    # BUG FIX (2026-09 audit): running this as an actual pytest test (not
    # just a CI-only shell step) means a developer who edits shared/ or
    # pipeline_function/ and forgets to re-mirror finds out the next time
    # they run `pytest` locally, well before it ever reaches CI or a manual
    # deploy. See scripts/verify_shared_mirror.sh for what this checks and
    # why the deploy-time risk itself is already handled by the copy step in
    # .github/workflows/catalyst-deploy.yml -- this closes the local-dev gap.
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "verify_shared_mirror.sh")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "functions/ps_1_cis_function is out of sync with shared/ and/or "
        "pipeline_function/. Run scripts/verify_shared_mirror.sh for details, "
        "then re-mirror as instructed there.\n\n"
        f"{result.stdout}\n{result.stderr}"
    )
