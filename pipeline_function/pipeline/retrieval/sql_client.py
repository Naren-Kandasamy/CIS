from shared.catalyst_client import ztsql_query

async def get_accused_stats(district: str = None) -> list:
    """
    Retrieves accused profile aggregates from ZTSQL.
    """
    query = """
        SELECT u.district_id as district, COUNT(a.accused_id) as total_accused, 
               AVG(a.prior_fir_count) as avg_priors
        FROM accused a
        JOIN cases c ON a.case_id = c.fir_internal_id
        JOIN units u ON c.unit_id = u.unit_id
    """
    params = []
    
    if district:
        query += " WHERE u.district_id = ?"
        params.append(district)
        
    query += " GROUP BY u.district_id"
    
    return await ztsql_query(query, params)

async def search_cases_by_district(district: str, limit: int = 50) -> list:
    """
    Structured filtering of cases in a district.
    """
    query = """
        SELECT c.fir_internal_id as id, c.crime_no, c.registered_date as date, 
               c.status, c.unit_id
        FROM cases c
        JOIN units u ON c.unit_id = u.unit_id
        WHERE u.district_id = ?
        LIMIT ?
    """
    return await ztsql_query(query, [district, limit])

# Additional retrieval functions will be added as DAG planner capabilities grow.
