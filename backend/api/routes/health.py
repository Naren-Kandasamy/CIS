from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
@router.head("/health")
async def health_check():
    """
    Cheap endpoint for keep-warm pings -- no Memgraph or Catalyst calls,
    no NoSQL reads beyond a trivial connectivity check.
    Pinged externally every 5 minutes (the exact AppSail instance
    lifetime) to prevent cold starts during operation/judging.
    """
    return {"status": "ok"}
