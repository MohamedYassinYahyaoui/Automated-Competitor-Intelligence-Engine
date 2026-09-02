import json
import duckdb
from datetime import datetime
from schemas import MarketAnalysis

DB_FILE = "analytics.duckdb"

def get_db_connection():
    """Connects to embedded DuckDB database file."""
    return duckdb.connect(DB_FILE)

def init_db():
    """Initializes the database schema if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_reports (
                id VARCHAR PRIMARY KEY,
                created_at TIMESTAMP,
                category_summary TEXT,
                price_assessment TEXT,
                raw_json JSON
            );
        """)

def save_report(report_id: str, analysis: MarketAnalysis) -> None:
    """Saves a Pydantic MarketAnalysis object into DuckDB."""
    with get_db_connection() as conn:
        # Convert Pydantic object to JSON string
        json_data = analysis.model_dump_json()
        
        conn.execute(
            """
            INSERT INTO market_reports (id, created_at, category_summary, price_assessment, raw_json)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                report_id,
                datetime.utcnow(),
                analysis.category_summary,
                analysis.price_assessment,
                json_data,
            ),
        )

def get_all_reports() -> list[dict]:
    """Retrieves all past reports ordered by newest first."""
    with get_db_connection() as conn:
        results = conn.execute("""
            SELECT id, created_at, category_summary, price_assessment, raw_json 
            FROM market_reports 
            ORDER BY created_at DESC;
        """).fetchall()
        
        reports = []
        for row in results:
            reports.append({
                "id": row[0],
                "created_at": row[1].isoformat(),
                "category_summary": row[2],
                "price_assessment": row[3],
                "full_report": json.loads(row[4]),
            })
        return reports