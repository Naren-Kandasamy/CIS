from abc import ABC, abstractmethod
from datetime import datetime

class CDRProvider(ABC):
    @abstractmethod
    async def fetch_call_records(self, phone_number: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{caller, callee, timestamp, duration_sec, tower_id, source_provenance}, ...]"""

    @abstractmethod
    async def fetch_ping_records(self, phone_number: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{phone_number, tower_id, timestamp, source_provenance}, ...]"""
        
    @abstractmethod
    async def fetch_device_usage(self, imei: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{imei, phone_number, activated_at, deactivated_at, source_provenance}, ...]"""

class FinancialProvider(ABC):
    @abstractmethod
    async def fetch_transactions(self, account_id: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{from_account, to_account, amount, timestamp, channel, pattern_tag, source_provenance}, ...]"""

class ANPRProvider(ABC):
    @abstractmethod
    async def fetch_plate_reads(self, plate_number: str,
                                 start: datetime, end: datetime) -> list[dict]:
        """Returns [{plate_number, camera_id, lat, lon, timestamp, speed, source_provenance}, ...]"""
