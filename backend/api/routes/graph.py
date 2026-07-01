from fastapi import APIRouter

router = APIRouter()

@router.get("/api/graph")
async def get_graph():
    # Will query Memgraph and return JSON for Cytoscape
    # For Phase 1, just a stub
    return {"nodes": [], "edges": []}
