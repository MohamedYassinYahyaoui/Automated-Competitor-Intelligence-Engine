import json
import logging
from typing import List, Optional
from google import genai
from google.genai import types
from pydantic import ValidationError
from dotenv import load_dotenv

from app.schemas import MarketReportSchema, OpenLibraryBook

load_dotenv()  # Load environment variables from .env file

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Initialize Gemini Client (Expects GEMINI_API_KEY environment variable)
ai_client = genai.Client()


async def generate_batch_market_report(
    batch: List[OpenLibraryBook],
) -> Optional[MarketReportSchema]:
    """
    Synthesizes a batch of validated book records into a structured market analysis report using Gemini.
    """
    if not batch:
        logging.warning("Empty batch passed to analyzer. Skipping LLM call.")
        return None

    # 1. Build a lightweight payload to optimize token consumption and context window usage
    condensed_payload = [
        {
            "key": book.key,
            "title": book.title,
            "subjects": book.subjects[:5],  # Limit subjects to top 5
        }
        for book in batch
    ]

    prompt = f"""
    Analyze the following batch of {len(condensed_payload)} book listings and generate a structured market report.
    
    Target Dataset:
    {json.dumps(condensed_payload, indent=2)}
    """

    system_instruction = """
    You are a senior publishing and competitor intelligence analyst. 
    Analyze the provided raw batch of book listings and synthesize key insights.
    Evaluate subject concentration, potential commercial value, market positioning, and critical takeaways.
    You MUST adhere strictly to the JSON schema specified for the output.
    """

    try:
        logging.info(
            f"Dispatching LLM synthesis request for batch of {len(batch)} items..."
        )

        # 2. Call Gemini enforcing Pydantic Schema output
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MarketReportSchema,
                system_instruction=system_instruction,
                temperature=0.2,  # Low temperature for factual, deterministic analysis
            ),
        )

        # 3. Validate raw JSON response against Pydantic model
        # Ensure response.text exists before parsing
        if not response.text:
            logging.error("LLM returned an empty response.")
            return None

        report_data = MarketReportSchema.model_validate_json(response.text)
        logging.info("Successfully synthesized and validated batch market report.")
        return report_data

    except ValidationError as ve:
        logging.error(f"LLM output failed Pydantic schema validation: {ve}")
        return None
    except Exception as err:
        logging.error(f"Failed to generate LLM market report: {err}")
        return None