import uuid
from datetime import datetime
from shared.data_sources.config import get_anpr_provider
from shared.graph_client import run_write, run_write_batch
from shared.review_queue_engine import push_review_item
from shared.review_queue_models import ReviewQueueItem
from shared.models import WantedVehicleRecord

# Mock lookup for wanted vehicles since we don't have a full NoSQL table seeded for this in the demo yet
WANTED_VEHICLES_MOCK = {}

async def get_wanted_vehicle(plate_number: str) -> WantedVehicleRecord | None:
    return WANTED_VEHICLES_MOCK.get(plate_number)

async def ingest_and_check_anpr(plate_number: str, start: datetime, end: datetime):
    provider = get_anpr_provider()
async def push_anpr_records_to_graph(reads: list[dict]):
    if not reads:
        return
    
    # We can inject the plate_number directly into each dict if not present,
    # but the synthetic provider always includes it.
    await run_write("""
        UNWIND $batch AS row
        MERGE (v:Vehicle {plate_number: row.plate_number})
        MERGE (c:ANPRCamera {camera_id: row.camera_id})
        SET c.lat = row.lat, c.lon = row.lon
        CREATE (v)-[h:DETECTED {timestamp: row.timestamp, speed: row.speed,
                                 source_provenance: row.source_provenance}]->(c)
    """, {"batch": reads})

    plate_number = reads[0].get("plate_number", "")
    wanted = await get_wanted_vehicle(plate_number)
    if wanted and reads:
        # Sort by timestamp to get latest read
        sorted_reads = sorted(reads, key=lambda x: x["timestamp"])
        latest_read = sorted_reads[-1]
        
        item = ReviewQueueItem(
            item_id=str(uuid.uuid4()),
            item_type="anpr_wanted_hit",
            fir_id=wanted.fir_id or "unknown",
            summary=(f"Wanted vehicle {plate_number} ({wanted.reason}) detected "
                     f"at {latest_read['camera_id']} on {latest_read['timestamp']}"),
            created_date=datetime.utcnow().isoformat()
        )
        await push_review_item(item)

async def ingest_and_check_anpr(plate_number: str, start: datetime, end: datetime):
    provider = get_anpr_provider()
    reads = await provider.fetch_plate_reads(plate_number, start, end)
    await push_anpr_records_to_graph(reads)
