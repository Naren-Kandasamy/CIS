"""
Shim for job status helpers used by the deployed Catalyst Function.

The deployed function cannot import from `backend` (an AppSail-only package).
This shim re-implements the same read/write helpers using only `shared/`, which
IS bundled into the function folder at deploy time.
"""
import json
from shared.catalyst_client import nosql_get, nosql_set

# Re-export nosql_get/nosql_set so main.py's single import line works unchanged
__all__ = ["write_job_status", "read_job_status", "nosql_get", "nosql_set"]


async def read_job_status(job_id: str):
    doc = await nosql_get(f"job:{job_id}")
    if doc and "value" in doc:
        return json.loads(doc["value"])
    return None


async def write_job_status(
    job_id: str,
    session_id: str = None,
    query: str = None,
    status: str = None,
    result: dict = None,
    error: str = None,
):
    job = await read_job_status(job_id) or {}
    if session_id is not None:
        job["session_id"] = session_id
    if query is not None:
        job["query"] = query
    if status is not None:
        job["status"] = status
    if result is not None:
        job["result"] = result
    if error is not None:
        job["error"] = error
    await nosql_set(f"job:{job_id}", json.dumps(job))
