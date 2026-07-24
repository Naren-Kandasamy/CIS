"""
ANPR Camera Read Ingestion & Wanted Vehicle Cross-Referencing Pipeline.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 5.
"""
import uuid
import logging
from datetime import datetime, timezone
from shared.data_sources.config import get_anpr_provider
from shared.graph_client import run_write
from shared.anpr_engine import get_wanted_vehicle
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item

logger = logging.getLogger(__name__)

async def ingest_and_check_anpr(plate_number: str, start: datetime, end: datetime) -> ReviewQueueItem | None:
    """
    1. Fetches ANPR plate reads from provider.
    2. Writes (v:Vehicle)-[:ANPR_HIT]->(l:Location) edges into Memgraph.
    3. Cross-references against WantedVehicleRecord registry.
    4. Pushes ReviewQueueItem alert (item_type="anpr_wanted_hit") if wanted.
    """
    provider = get_anpr_provider()
    reads = await provider.fetch_plate_reads(plate_number, start, end)
    
    if not reads:
        logger.info("No ANPR reads found for plate %s in time window.", plate_number)
        return None

    # Write ANPR_HIT relationships to graph
    for r in reads:
        try:
            await run_write("""
                MERGE (v:Vehicle {plate_number: $plate_number})
                MERGE (l:Location {id: $camera_id})
                ON CREATE SET l.lat = $lat, l.lon = $lon, l.name = $camera_id
                MERGE (v)-[h:ANPR_HIT {timestamp: $timestamp}]->(l)
                SET h.camera_id = $camera_id,
                    h.source_provenance = $source_provenance
            """, {
                "plate_number": r["plate_number"],
                "camera_id": r["camera_id"],
                "lat": r["lat"],
                "lon": r["lon"],
                "timestamp": r["timestamp"],
                "source_provenance": r["source_provenance"]
            })
        except Exception as e:
            logger.error("Failed to write ANPR_HIT to graph for plate %s: %s", r["plate_number"], e)

    # Check wanted vehicle registry
    wanted = await get_wanted_vehicle(plate_number)
    if wanted:
        latest_read = reads[-1]  # reads are sorted chronologically
        item = ReviewQueueItem(
            item_id=str(uuid.uuid4()),
            item_type="anpr_wanted_hit",
            fir_id=wanted.fir_id or "UNKNOWN_CASE",
            summary=(
                f"Wanted vehicle {plate_number} ({wanted.reason}) detected by "
                f"camera {latest_read['camera_id']} at {latest_read['timestamp']}"
            ),
            score=0.95,  # high confidence deterministic plate match
            created_date=datetime.now(timezone.utc).isoformat(),
        )
        await push_review_item(item)
        logger.info("Generated anpr_wanted_hit alert %s for plate %s", item.item_id, plate_number)
        return item

    return None
