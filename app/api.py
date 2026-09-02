from typing import Any, Dict, List, Optional
import duckdb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(
    title="Market Analysis API",
    description="Exposes DuckDB analytical data and LLM-generated market reports.",
    version="1.0.0",
)

DB_FILE = "analytics.duckdb"


# ---------------------------------------------------------------------------
# RESPONSE SCHEMAS
# ---------------------------------------------------------------------------
class MarketReportResponse(BaseModel):
    id: str
    created_at: str
    batch_size: Optional[int] = None
    category_summary: Optional[str] = None
    price_assessment: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None


class RawBookResponse(BaseModel):
    key: str
    title: str
    subjects: List[str]


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def get_db_connection():
    """Connect to DuckDB in read-only mode to prevent locking conflicts with main.py."""
    try:
        return duckdb.connect(DB_FILE, read_only=True)
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to analytical storage: {err}",
        )


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/")
def health_check():
    """Basic health check endpoint."""
    return {"status": "online", "database": DB_FILE}


@app.get("/reports/latest", response_model=MarketReportResponse)
def get_latest_report():
    """Returns the most recent LLM-generated market synthesis report."""
    con = get_db_connection()
    try:
        query = """
            SELECT id, CAST(created_at AS VARCHAR) as created_at, batch_size, 
                   category_summary, price_assessment, raw_json
            FROM market_reports
            ORDER BY created_at DESC
            LIMIT 1
        """
        result = con.execute(query).fetchone()
        con.close()

        if not result:
            raise HTTPException(
                status_code=404, detail="No market reports found in storage."
            )

        return MarketReportResponse(
            id=str(result[0]),
            created_at=result[1],
            batch_size=result[2],
            category_summary=result[3],
            price_assessment=result[4],
            raw_json=result[5] if isinstance(result[5], dict) else None,
        )
    except Exception as err:
        con.close()
        raise HTTPException(status_code=500, detail=str(err))


@app.get("/reports", response_model=List[MarketReportResponse])
def list_reports(limit: int = Query(default=10, ge=1, le=100)):
    """Returns a paginated list of historical market reports."""
    con = get_db_connection()
    try:
        query = """
            SELECT id, CAST(created_at AS VARCHAR) as created_at, batch_size, 
                   category_summary, price_assessment, raw_json
            FROM market_reports
            ORDER BY created_at DESC
            LIMIT ?
        """
        results = con.execute(query, [limit]).fetchall()
        con.close()

        reports = []
        for row in results:
            reports.append(
                MarketReportResponse(
                    id=str(row[0]),
                    created_at=row[1],
                    batch_size=row[2],
                    category_summary=row[3],
                    price_assessment=row[4],
                    raw_json=row[5] if isinstance(row[5], dict) else None,
                )
            )
        return reports
    except Exception as err:
        con.close()
        raise HTTPException(status_code=500, detail=str(err))


@app.get("/books", response_model=List[RawBookResponse])
def list_ingested_books(limit: int = Query(default=20, ge=1, le=100)):
    """Returns raw ingested books from the analytical table."""
    con = get_db_connection()
    try:
        query = "SELECT key, title, subjects FROM raw_books LIMIT ?"
        results = con.execute(query, [limit]).fetchall()
        con.close()

        books = []
        for row in results:
            books.append(
                RawBookResponse(
                    key=row[0], title=row[1], subjects=row[2] if row[2] else []
                )
            )
        return books
    except Exception as err:
        con.close()
        raise HTTPException(status_code=500, detail=str(err))