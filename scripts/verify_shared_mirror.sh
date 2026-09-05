#!/usr/bin/env bash
# BUG FIX (2026-09 audit): the deploy workflow (.github/workflows/catalyst-deploy.yml)
# already regenerates functions/ps_1_cis_function/{shared,pipeline_function}
# fresh from the top-level shared/ and pipeline_function/ immediately before
# every deploy, so a stale *committed* mirror was never actually a deploy-time
# risk. The real risk is local: anyone running or debugging
# functions/ps_1_cis_function directly (catalyst functions:execute locally,
# reading it while investigating a bug, a one-off manual deploy without going
# through CI) can silently be looking at, or shipping, code that no longer
# matches shared/ or pipeline_function/ if a developer edited those without
# remembering to re-copy. This script makes that check a one-liner instead of
# a "remember to run diff -rq" step buried in the README, so it can be wired
# into a pre-commit hook or run on demand before a manual deploy.
#
# Usage: ./scripts/verify_shared_mirror.sh
# Exit 0  -- mirror is in sync.
# Exit 1  -- mirror is stale; prints exactly what differs and the fix command.

set -euo pipefail
cd "$(dirname "$0")/.."

STALE=0

check() {
    local src="$1"
    local dst="$2"
    if [ ! -d "$dst" ]; then
        echo "MISSING: $dst does not exist yet."
        STALE=1
        return
    fi
    if ! diff -rq "$src" "$dst" --exclude=__pycache__ --exclude="*.pyc" > /tmp/mirror_diff_$$.txt 2>&1; then
        echo "STALE: $dst does not match $src"
        cat /tmp/mirror_diff_$$.txt
        STALE=1
    fi
    rm -f /tmp/mirror_diff_$$.txt
}

check shared functions/ps_1_cis_function/shared
check pipeline_function functions/ps_1_cis_function/pipeline_function

if [ "$STALE" -ne 0 ]; then
    echo ""
    echo "functions/ps_1_cis_function is out of sync. Re-mirror with:"
    echo "  rm -rf functions/ps_1_cis_function/shared && cp -r shared functions/ps_1_cis_function/"
    echo "  rm -rf functions/ps_1_cis_function/pipeline_function && cp -r pipeline_function functions/ps_1_cis_function/"
    exit 1
fi

echo "OK: functions/ps_1_cis_function mirror matches shared/ and pipeline_function/."
exit 0
