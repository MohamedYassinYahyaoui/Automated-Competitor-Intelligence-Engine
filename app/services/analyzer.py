import logging
from google import genai
from google.genai import types
import duckdb
from app.core.config import settings
from app.schemas.book import BookRecord


def analyze_batch(records: list[BookRecord]) -> str:
    """Passes ingested product records to Gemini 2.5 Flash for market intelligence extraction."""
    
    # Filter out zero-priced placeholder items (e.g. Free Returns Coverage)
    valid_priced_records = [r for r in records if r.price > 0.0]
    
    if not valid_priced_records:
        logging.warning("[ANALYZER GUARDRAIL] Aborting synthesis: 0 records contain non-zero pricing data.")
        return "Synthesis skipped: No valid non-zero pricing data found in ingested batch."

    # Construct clean payload for Gemini context
    context_payload = [
        {
            "product_id": r.key,
            "product_title": r.title,
            "price_usd": f"${r.price:.2f}",
            "vendor": r.vendor,
            "category": r.category,
        }
        for r in valid_priced_records
    ]

    prompt = f"""
    You are a competitive intelligence analyst. Analyze the following e-commerce product batch:

    {context_payload}

    Provide a concise synthesis covering:
    1. Category Summary: Primary product categories and vendor concentration.
    2. Price Assessment: Specific price ranges, median price points, and premium vs budget positioning.
    3. Strategic Takeaways: Key market opportunities or pricing anomalies.
    """

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1000,
        ),
    )

    return response.text