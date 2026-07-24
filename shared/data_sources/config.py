"""
Data Source Provider Factory & Configuration.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.1.
"""
import os
from shared.data_sources.base import ANPRProvider

DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "synthetic")  # "synthetic" | "production"

def get_anpr_provider() -> ANPRProvider:
    if DATA_SOURCE_MODE == "synthetic":
        from shared.data_sources.synthetic_anpr import SyntheticANPRProvider
        return SyntheticANPRProvider()
    raise NotImplementedError(
        "Production ANPR provider requires live camera integration feed — "
        "not configured in synthetic demo mode."
    )
