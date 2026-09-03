import json
import logging
import duckdb
from google import genai
from google.genai import types
from app.core.config import settings
from app.schemas.book import BookRecord
from app.schemas.report import SynthesizedReport


def analyze_batch(records: list[BookRecord]) -> SynthesizedReport | None:
    """Feeds valid ingested items into Gemini for structured competitive synthesis."""
    if not records:
        logging.warning("No valid records supplied for Gemini synthesis. Aborting.")
        return None

    context_payload = [
        {"title": r.title, "description": r.description[:200], "subjects": r.subjects}
        for r in records
    ]

    prompt = f"""
    You are a high-level competitive intelligence analyst.
    Analyze the target product records and summarize key market insights.
    
    CRITICAL: You MUST respond strictly with a valid JSON object matching the requested schema. 
    Do NOT include introductory conversational text, explanations, or markdown code blocks.

    Target Data Batch:
    {json.dumps(context_payload, indent=2)}
    """

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SynthesizedReport,
                temperature=0.1,
            ),
        )

        # Clean potential markdown wrappers if returned by model
        raw_text = (response.text or "").strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.removeprefix("```json").removesuffix("```").strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.removeprefix("```").removesuffix("```").strip()

        # Validate structured json output
        structured_data = SynthesizedReport.model_validate_json(raw_text)

        # Persist report to DuckDB
        with duckdb.connect(settings.DB_PATH) as con:
            con.execute(
                """
                INSERT INTO market_reports (batch_size, category_summary, price_assessment, raw_json)
                VALUES (?, ?, ?, ?)
            """,
                [
                    len(records),
                    structured_data.category_summary,
                    structured_data.price_assessment,
                    structured_data.model_dump_json(),
                ],
            )

        logging.info("Successfully generated and stored market intelligence report.")
        return structured_data

    except Exception as err:
        logging.error(f"Failed to generate Gemini analysis: {err}")
        return None