from shared.catalyst_client import ztsql_query

async def get_accused_stats(district: str = None) -> list:
    """
    Retrieves accused profile aggregates from ZTSQL.
    Example placeholder for SQL retrieval inside the pipeline.
    """
    # TODO: verify column names against ZTSQL schema §15.
    # Note: KSP schema routes district through unit_id -> Unit -> DistrictID, not a flat column.
    query = "SELECT district, COUNT(accused_id) as total_accused, AVG(prior_fir_count) as avg_priors FROM accused"
    params = []
    
    if district:
        query += " WHERE district = ?"
        params.append(district)
        
    query += " GROUP BY district"
    
    return await ztsql_query(query, params)

async def search_cases_by_district(district: str, limit: int = 50) -> list:
    """
    Structured filtering of cases in a district.
    """
    # TODO: verify column names against ZTSQL schema §15 (e.g., id vs fir_internal_id).
    # Note: Cases are linked to districts via unit_id -> Unit -> DistrictID, joining is required.
    query = "SELECT id, crime_no, date, status, unit_id FROM cases WHERE district = ? LIMIT ?"
    return await ztsql_query(query, [district, limit])

# Additional retrieval functions will be added as DAG planner capabilities grow.
