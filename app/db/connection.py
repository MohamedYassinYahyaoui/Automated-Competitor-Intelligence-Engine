import duckdb
import logging
from app.core.config import settings

def init_db():
    with duckdb.connect(settings.DB_PATH) as con:
        # Recreate raw_books table
        con.execute("""
            CREATE TABLE IF NOT EXISTS raw_books (
                key VARCHAR PRIMARY KEY,
                title VARCHAR,
                description VARCHAR,
                price DOUBLE DEFAULT 0.0,
                vendor VARCHAR DEFAULT 'Unknown',
                category VARCHAR DEFAULT 'General',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Recreate dead_letter_queue table
        con.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id VARCHAR PRIMARY KEY,
                source_url VARCHAR,
                raw_payload VARCHAR,
                error_message VARCHAR,
                quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    logging.info(f"Database initialized successfully at '{settings.DB_PATH}'.")