import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from schemas import MarketAnalysis
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="google.genai")
# Load environment variables from .env
load_dotenv()

# Instantiate the client (automatically uses GEMINI_API_KEY env var)
client = genai.Client()

def analyze_extracted_books(books_data: list[dict]) -> MarketAnalysis:
    """Sends scraped book data to Gemini and returns a validated Pydantic model."""
    
    prompt = f"""
    You are a market analyst examining real-time scraping data.
    Analyze the following list of books extracted from our scraper:
    {books_data}
    
    Provide an analysis adhering strictly to the structured output format requested.
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MarketAnalysis,
            temperature=0.2, # Low temperature for more deterministic schema adherence
        ),
    )
    
    # Parse and validate the raw JSON text directly into the Pydantic model
    response_text = response.text
    if response_text is None or response_text == "":
        raise ValueError("Gemini API returned an empty response body.")

    validated_analysis = MarketAnalysis.model_validate_json(response_text)
    return validated_analysis