import uuid
import warnings
from typing import List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl

# Ignore SDK warnings
warnings.filterwarnings("ignore", category=UserWarning, module="google.genai")

from scraper import fetch_all_urls, parse_book_html
from analyzer import analyze_extracted_books
from database import init_db, save_report, get_all_reports
from schemas import MarketAnalysis

# Instantiate FastAPI application
app = FastAPI(
    title="Automated Competitor Intelligence Engine",
    description="Asynchronous web scraper with Gemini structured AI analysis and DuckDB storage.",
    version="1.0.0",
)

# Initialize database table on server startup
@app.on_event("startup")
def on_startup():
    init_db()

class AnalysisRequest(BaseModel):
    urls: List[HttpUrl]

class AnalysisResponse(BaseModel):
    report_id: str
    status: str
    analysis: MarketAnalysis

@app.get("/")
def read_root():
    return {"status": "online", "message": "Competitor Intelligence API is running."}

@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def trigger_analysis(request: AnalysisRequest):
    """
    Accepts a list of target URLs, scrapes page HTML, passes data to Gemini,
    saves structured output to DuckDB, and returns the response.
    """
    str_urls = [str(url) for url in request.urls]
    
    try:
        # Step 1: Execute concurrent scraping
        html_pages = await fetch_all_urls(str_urls)
        raw_books = [book for html in html_pages for book in parse_book_html(html)]
        
        if not raw_books:
            raise HTTPException(status_code=422, detail="No valid product records found from provided URLs.")
        
        # Step 2: Run Gemini analysis
        analysis_result: MarketAnalysis = analyze_extracted_books(raw_books)
        
        # Step 3: Store in DuckDB
        report_id = str(uuid.uuid4())
        save_report(report_id, analysis_result)
        
        return AnalysisResponse(
            report_id=report_id,
            status="completed",
            analysis=analysis_result
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline processing failed: {str(e)}")

@app.get("/api/v1/reports")
def list_reports():
    """Returns all historical intelligence reports stored in DuckDB."""
    return {"count": len(get_all_reports()), "reports": get_all_reports()}