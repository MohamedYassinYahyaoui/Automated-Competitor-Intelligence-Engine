# Automated Competitor Intelligence Engine

An intelligent system for gathering, analyzing, and reporting on competitor market activities in real-time.

## Overview

This project automates the collection and analysis of competitor data from various sources, providing actionable insights through a RESTful API and comprehensive reporting system.

## Features

- **Data Ingestion**: Automated collection of competitor product and pricing data
- **Real-time Analysis**: Process and analyze competitor information instantly
- **RESTful API**: FastAPI-based endpoints for accessing intelligence data
- **Dead Letter Queue (DLQ)**: Robust error handling and retry mechanism for failed ingestions
- **DuckDB Storage**: Efficient local data warehousing with SQL query capabilities
- **Report Generation**: Structured reporting on competitor analysis

## Project Structure

```
├── app/                          # Main application package
│   ├── api/
│   │   └── router.py            # API route definitions
│   ├── core/
│   │   └── config.py            # Configuration management
│   ├── db/
│   │   ├── connection.py        # Database connection handler
│   │   └── dlq.py               # Dead Letter Queue implementation
│   ├── schemas/
│   │   ├── book.py              # Book data schema
│   │   ├── dlq.py               # DLQ schema
│   │   └── report.py            # Report schema
│   └── services/
│       ├── analyzer.py          # Data analysis logic
│       └── ingestion.py         # Data ingestion logic
├── scripts/
│   └── replay_dlq.py            # Utility to replay DLQ messages
├── main.py                       # Application entry point
├── requirement.txt              # Project dependencies
├── analytics.duckdb             # DuckDB database file
└── README.md                     # This file
```

## Prerequisites

- Python 3.8+
- pip (Python package manager)

## Setup Instructions

1. **Create Virtual Environment**
   ```bash
   python -m venv myenv
   ```

2. **Activate Virtual Environment**
   - On Windows:
     ```bash
     myenv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source myenv/bin/activate
     ```

3. **Install Dependencies**
   ```bash
   pip install -r requirement.txt
   ```

## Running the Application

Start the API server:
```bash
python main.py
```

The API will be available at `http://localhost:8000` (default FastAPI configuration).

## Key Components

### Database (`app/db/`)
- **connection.py**: Manages DuckDB connections and query execution
- **dlq.py**: Implements Dead Letter Queue for handling failed operations

### Services (`app/services/`)
- **ingestion.py**: Handles data collection from competitor sources
- **analyzer.py**: Processes and analyzes collected data

### Schemas (`app/schemas/`)
- **book.py**: Defines data structure for product/book information
- **report.py**: Defines reporting data structure
- **dlq.py**: Defines Dead Letter Queue message structure

### API (`app/api/`)
- **router.py**: Defines all RESTful API endpoints

## Utility Scripts

### replay_dlq.py
Replays failed messages from the Dead Letter Queue for reprocessing:
```bash
python scripts/replay_dlq.py
```

## Database

The application uses **DuckDB** for local data warehousing. The database file is stored as `analytics.duckdb`.

## Configuration

Configuration settings are managed in `app/core/config.py`. Update this file to customize:
- Database connections
- API settings
- Ingestion parameters
- Analysis thresholds

## Dependencies

Key dependencies (see `requirement.txt` for full list):
- **fastapi**: Web framework for building APIs
- **duckdb**: Embedded data warehouse
- **pydantic**: Data validation and settings management
- **httpx**: Async HTTP client for data collection

## Error Handling

Failed ingestions and processing errors are captured in the Dead Letter Queue (DLQ) system. Use the replay_dlq.py script to retry failed operations.



