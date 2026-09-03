# Automated Competitor Intelligence Engine

An enterprise-grade, asynchronous ETL and competitive intelligence pipeline built in Python. The engine continuously ingests raw e-commerce catalog payloads across target competitor domains, extracts and normalizes product attributes, persists analytical records into **DuckDB**, prunes payload context for token efficiency, and synthesizes executive market briefs using **Gemini 2.5 Flash**.

---

## Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                                 INGESTION LAYER                                   |
+-----------------------------------------------------------------------------------+
|  Allbirds (Shopify JSON)  |  Red Bull Shop (Shopify JSON)  | Gymshark (Stealth)   |
+---------------------------+---------------------------------+----------------------+
              |                             |                            |
              v                             v                            v
     [ Fast Path Request ]         [ Fast Path Request ]        [ Playwright Stealth ]
     (curl_cffi / HTTPX)           (curl_cffi / HTTPX)          (Bypass Anti-Bot/403)
              |                             |                            |
              +-----------------------------+----------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------+
|                              EXTRACTION & TRANSFORM                               |
+-----------------------------------------------------------------------------------+
|  - Fast Path JSON Parser & Resilient HTML Fallback                                |
|  - Schema Standardization (Title, Price, Variants, Availability, Category)        |
|  - Data Cleansing & Currency Normalization                                        |
+-----------------------------------------------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------+
|                             ANALYTICAL STORAGE (DuckDB)                           |
+-----------------------------------------------------------------------------------+
|  - Persistent OLAP Storage (analytics.duckdb)                                     |
|  - Schema Verification & Bulk Record Upserts                                      |
+-----------------------------------------------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------+
|                          CONTEXT PRUNING & LLM SYNTHESIS                          |
+-----------------------------------------------------------------------------------+
|  - Dynamic Token & Field Pruning (Reduces prompt overhead by ~60%)                |
|  - Asynchronous Dispatch to gemini-2.5-flash                                      |
|  - Structured Synthesis (Pricing Landscape, Assortment, OOS Gaps, Strategy)       |
+-----------------------------------------------------------------------------------+
```

---

## Key Features

- **Multi-Tiered Ingestion Pipeline** — Uses `curl_cffi` for high-throughput fast-path scraping, with an automated fallback to headless **Playwright** stealth browser instances to bypass anti-bot protections (Cloudflare 403s).
- **Embedded OLAP Storage (DuckDB)** — Stores catalog snapshots locally in a high-performance analytical database without the operational overhead of external database instances.
- **Context-Optimized LLM Prompting** — A custom payload-pruning layer strips non-essential metadata (raw HTML descriptions, duplicate imagery, platform tags) before sending context to **Gemini 2.5 Flash**, reducing token consumption and API latency.
- **Automated Intelligence Synthesis** — Generates executive briefs detailing price bands, variant density metrics, out-of-stock (OOS) risk levels, and actionable market strategies.

---

## Tech Stack

| Category | Tools |
|---|---|
| Language | Python 3.11+ |
| Ingestion & Scraping | `curl_cffi`, `playwright`, `httpx` |
| Data Persistence | `duckdb` |
| LLM Synthesis | `google-genai` (Gemini 2.5 Flash) |
| Environment Management | `python-dotenv` |

---

## Directory Structure

```text
Automated-Competitor-Intelligence-Engine/
├── app/
│   ├── services/
│   │   ├── __init__.py
│   │   ├── analyzer.py       # Gemini 2.5 Flash async integration
│   │   ├── extractor.py      # Resilient JSON/HTML catalog parser
│   │   ├── ingestion.py      # Multi-tiered scraper (curl_cffi + Playwright)
│   │   └── transform.py      # DuckDB persistence & payload token pruning
│   └── __init__.py
├── main.py                   # Async pipeline orchestrator
├── requirements.txt          # Production dependencies
├── .gitignore                # Environment and database exclusion rules
└── README.md
```

---

## Getting Started

### 1. Prerequisites

- Python 3.11 or higher
- PowerShell (Windows) or standard Bash (Linux/macOS)
- A Google Gemini API Key ([Get one via Google AI Studio](https://aistudio.google.com/))

### 2. Installation

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/Automated-Competitor-Intelligence-Engine.git
cd Automated-Competitor-Intelligence-Engine

# Create virtual environment
python -m venv myenv

# Activate virtual environment
# Windows PowerShell:
.\myenv\Scripts\Activate.ps1
# Linux/macOS:
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 3. Environment Configuration

Set your Gemini API key in your terminal session:

**PowerShell:**
```powershell
$env:GEMINI_API_KEY="your_actual_gemini_api_key_here"
```

**Bash / Linux:**
```bash
export GEMINI_API_KEY="your_actual_gemini_api_key_here"
```

---

## Execution

Run the complete ETL and synthesis pipeline:

```bash
python main.py
```

### Sample Pipeline Output

```text
2026-09-03 18:38:13,373 [INFO] orchestrator: Starting Automated Competitor Intelligence Engine pipeline execution...
2026-09-03 18:38:13,769 [INFO] orchestrator: Successfully extracted 10 products from Allbirds
2026-09-03 18:38:14,040 [INFO] orchestrator: Successfully extracted 10 products from Red Bull Shop
2026-09-03 18:38:14,447 [INFO] orchestrator: Successfully extracted 10 products from Gymshark US
2026-09-03 18:38:14,463 [INFO] app.services.transform: DuckDB analytical schema verified.
2026-09-03 18:38:15,012 [INFO] app.services.transform: Successfully persisted catalog items across targets into DuckDB.
2026-09-03 18:38:15,373 [INFO] app.services.analyzer: Dispatching payload context (13415 chars) to model 'gemini-2.5-flash'...
2026-09-03 18:38:37,459 [INFO] app.services.analyzer: Successfully generated competitive analysis brief.
```

---

## Database Inspection (DuckDB)

You can run SQL queries directly against the generated `analytics.duckdb` file using Python or the DuckDB CLI to inspect stored product metrics.

```python
import duckdb

conn = duckdb.connect("analytics.duckdb")

# Query pricing summary by target brand
query = """
SELECT 
    target_name,
    COUNT(*) as total_products,
    ROUND(AVG(price), 2) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price,
    SUM(CASE WHEN is_available = FALSE THEN 1 ELSE 0 END) as oos_count
FROM products
GROUP BY target_name;
"""

print(conn.execute(query).df())
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
