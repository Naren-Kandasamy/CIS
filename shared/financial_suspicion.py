from statistics import mean
from datetime import datetime

def nearest_threshold(amount: float) -> float:
    # Resolves to whichever of {50000, 100000, 1000000} the amount is closest to and below
    thresholds = [50000, 100000, 1000000]
    # Filter thresholds greater than or equal to amount
    valid_thresholds = [t for t in thresholds if t >= amount]
    if not valid_thresholds:
        return 1000000 # default to highest if above
    return min(valid_thresholds)

def compute_structuring_suspicion(txns: list[dict]) -> float:
    """
    Computes a weighted composite score [0.0, 1.0] for structuring behavior based on
    a list of transaction dictionaries for a given account.
    Expects txns to have 'amount', 'to_account', and 'timestamp'.
    """
    if not txns:
        return 0.0

    # 1. Threshold proximity
    proximity_scores = []
    for t in txns:
        amount = float(t['amount'])
        target = nearest_threshold(amount)
        # 1 - normalized distance to threshold
        score = 1 - (abs(amount - target) / target)
        proximity_scores.append(score)
    
    proximity_score = mean(proximity_scores) if proximity_scores else 0.0

    # 2. Repetition
    repetition_score = min(len(txns) / 5.0, 1.0)

    # 3. Destination concentration (fan-out/fan-in shape)
    recipients = set(t['to_account'] for t in txns)
    concentration_score = 1.0 - (len(recipients) / len(txns))

    # 4. Time clustering
    # Calculate how tightly clustered the transactions are in time
    # If all txns happen in < 1 hour, tight=1.0. If spread over > 7 days, tight=0.0
    if len(txns) > 1:
        timestamps = [datetime.fromisoformat(t['timestamp']) for t in txns]
        delta_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0
        # Normalizing to a 7 day (168 hour) window
        if delta_hours == 0:
            time_clustering_score = 1.0
        else:
            time_clustering_score = max(0.0, 1.0 - (delta_hours / 168.0))
    else:
        time_clustering_score = 0.0

    # Weighted composite
    final_score = (
        0.35 * proximity_score +
        0.25 * repetition_score +
        0.25 * concentration_score +
        0.15 * time_clustering_score
    )
    
    return min(1.0, max(0.0, final_score))
