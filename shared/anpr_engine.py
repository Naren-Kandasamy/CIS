"""
ANPR & Wanted Vehicle Registry Data Engine.
Persists and checks wanted vehicle records in NoSQL datastore.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 5.
"""
import json
import logging
from shared.catalyst_client import nosql_get, nosql_set
from shared.anpr_models import WantedVehicleRecord

logger = logging.getLogger(__name__)

async def register_wanted_vehicle(record: WantedVehicleRecord):
    """Register a wanted/stolen vehicle in the NoSQL registry."""
    key = f"wanted_vehicle:{record.plate_number.replace(' ', '_')}"
    try:
        data_str = record.model_dump_json()
    except AttributeError:
        data_str = record.json()
    await nosql_set(key, data_str)
    logger.info("Registered wanted vehicle: %s (%s)", record.plate_number, record.reason)

async def get_wanted_vehicle(plate_number: str) -> WantedVehicleRecord | None:
    """Retrieve a wanted vehicle record by plate number if present."""
    key = f"wanted_vehicle:{plate_number.replace(' ', '_')}"
    raw = await nosql_get(key)
    if not raw:
        return None
    val = raw.get("value") if isinstance(raw, dict) else raw
    if not val:
        return None
    try:
        data = json.loads(val) if isinstance(val, str) else val
        return WantedVehicleRecord(**data)
    except Exception as e:
        logger.error("Failed to parse WantedVehicleRecord for key %s: %s", key, e)
        return None
