import uuid
from datetime import datetime
from shared.data_sources.config import get_cdr_provider, get_financial_provider
from shared.graph_client import run_write, run_write_batch

async def ingest_call_records(phone_number: str, start: datetime, end: datetime):
    provider = get_cdr_provider()
async def push_call_records_to_graph(records: list[dict]):
    if not records:
        return
    await run_write("""
        UNWIND $batch AS row
        MERGE (a:Phone {number: row.caller})
        MERGE (b:Phone {number: row.callee})
        MERGE (a)-[c:CALLED {timestamp: row.timestamp}]->(b)
        SET c.duration_sec = row.duration_sec, c.tower_id = row.tower_id,
            c.source_provenance = row.source_provenance
    """, {"batch": records})

async def push_ping_records_to_graph(records: list[dict]):
    if not records:
        return
    await run_write("""
        UNWIND $batch AS row
        MERGE (p:Phone {number: row.phone_number})
        MERGE (t:CellTower {tower_id: row.tower_id})
        MERGE (p)-[c:PINGED {timestamp: row.timestamp}]->(t)
        SET c.source_provenance = row.source_provenance
    """, {"batch": records})

    # Device usage (IMEI churn)
async def push_device_records_to_graph(records: list[dict]):
    if not records:
        return
    await run_write("""
        UNWIND $batch AS row
        MERGE (d:Device {imei: row.imei})
        MERGE (p:Phone {number: row.phone_number})
        MERGE (d)-[c:USED_AS {activated_at: row.activated_at, deactivated_at: row.deactivated_at}]->(p)
        SET c.source_provenance = row.source_provenance
    """, {"batch": records})

async def ingest_call_records(phone_number: str, start: datetime, end: datetime):
    provider = get_cdr_provider()
    records = await provider.fetch_call_records(phone_number, start, end)
    await push_call_records_to_graph(records)
    
    ping_records = await provider.fetch_ping_records(phone_number, start, end)
    await push_ping_records_to_graph(ping_records)
    
    device_records = await provider.fetch_device_usage("", start, end) 
    await push_device_records_to_graph(device_records)

async def ingest_financial_records(account_id: str, start: datetime, end: datetime):
    provider = get_financial_provider()
async def push_financial_records_to_graph(records: list[dict]):
    if not records:
        return
    await run_write("""
        UNWIND $batch AS row
        MERGE (a:Account {account_id: row.from_account})
        MERGE (b:Account {account_id: row.to_account})
        MERGE (a)-[t:TRANSFERRED {timestamp: row.timestamp}]->(b)
        SET t.amount = row.amount, t.channel = row.channel,
            t.pattern_tag = row.pattern_tag,
            t.source_provenance = row.source_provenance
    """, {"batch": records})

async def ingest_financial_records(account_id: str, start: datetime, end: datetime):
    provider = get_financial_provider()
    records = await provider.fetch_transactions(account_id, start, end)
    await push_financial_records_to_graph(records)
