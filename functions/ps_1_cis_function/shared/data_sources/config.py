import os

DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "synthetic")  # "synthetic" | "production"

def get_cdr_provider():
    if DATA_SOURCE_MODE == "synthetic":
        from shared.data_sources.synthetic_cdr import SyntheticCDRProvider
        return SyntheticCDRProvider()
    raise NotImplementedError(
        "Production CDR provider requires a real lawful-access integration -- "
        "not something to stub in. Wire in the actual telecom-operator integration here."
    )

def get_financial_provider():
    if DATA_SOURCE_MODE == "synthetic":
        from shared.data_sources.synthetic_financial import SyntheticFinancialProvider
        return SyntheticFinancialProvider()
    raise NotImplementedError("Production Financial provider requires a real bank/UPI integration.")

def get_anpr_provider():
    if DATA_SOURCE_MODE == "synthetic":
        from shared.data_sources.synthetic_anpr import SyntheticANPRProvider
        return SyntheticANPRProvider()
    raise NotImplementedError("Production ANPR provider requires a real traffic camera network integration.")
