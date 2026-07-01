import asyncio
import json

SSE_MAX_POLL_SECONDS = 120  # 2-minute client timeout guard
SSE_POLL_INTERVAL    = 0.5  # seconds between NoSQL reads

async def stream_job_status(job_id: str):
    """
    Polls the Catalyst NoSQL job document on a short interval and forwards
    meaningful status transitions as SSE events. The pipeline Function (not
    this endpoint) is what actually advances `status` through the pipeline stages.
    """
    from backend.job_dispatch import read_job_status
    last_status = None
    elapsed = 0.0

    while elapsed < SSE_MAX_POLL_SECONDS:
        job = await read_job_status(job_id)

        if job and job.get("status") != last_status:
            last_status = job["status"]
            yield {"event": "progress", "data": json.dumps({"status": job["status"]})}

        if job and job.get("status") == "done":
            result = job.get("result") or {}
            yield {"event": "evidence", "data": json.dumps(result.get("evidence", []))}
            if result.get("visualization"):
                yield {"event": "visualization", "data": json.dumps(result["visualization"])}
            yield {"event": "token", "data": json.dumps({"token": result.get("answer", "")})}
            yield {"event": "done", "data": "{}"}
            return

        if job and job.get("status") == "failed":
            yield {"event": "error", "data": json.dumps({"error": job.get("error")})}
            return

        # Keepalive: SSE comment line (: ping) keeps the TCP connection open
        # and prevents sse_starlette from closing the generator during long
        # LLM retry windows (can be 5-8s per retry attempt).
        yield {"event": "ping", "data": json.dumps({"t": round(elapsed, 1)})}

        await asyncio.sleep(SSE_POLL_INTERVAL)
        elapsed += SSE_POLL_INTERVAL

    # BUG FIX: without this guard, a job that never transitions to done/failed
    # (e.g. pipeline Function silently crashed without writing status) would
    # hold the SSE connection open until the AppSail 30s HTTP timeout kills it
    # ungracefully. Now we close the stream cleanly after SSE_MAX_POLL_SECONDS.
    yield {"event": "error", "data": json.dumps({"error": "Job timed out waiting for pipeline response"})}
