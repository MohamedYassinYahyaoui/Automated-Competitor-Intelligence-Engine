import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, List
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """
You are a senior e-commerce intelligence analyst specializing in competitor benchmarking and dynamic pricing strategy.
Your task is to analyze pruned multi-brand product catalogs and generate a executive intelligence brief.

Your output must be structured, objective, and focus heavily on actionable insights:
1. Pricing Landscape: Compare min/max/average price bands across tracked targets. Highlight anomalies or aggressive positioning.
2. Assortment & Catalog Breadth: Analyze total catalog size, dominant categories, and variant density.
3. Inventory & Availability: Identify out-of-stock trends or stock concentration risks.
4. Strategic Opportunities: Provide 3 concrete recommendations for competing against these brands.

Do not fabricate data. Strictly base your analysis on the provided structured payload.
"""

async def generate_intelligence_report(
    pruned_payload: List[Dict[str, Any]],
    model_name: str = "gemini-2.5-flash"
) -> str:
    """
    Asynchronously passes the pruned catalog payload to Gemini 2.5 Flash
    to synthesize strategic competitor intelligence.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable is missing.")
        raise ValueError("GEMINI_API_KEY environment variable is required to run analyzer.py.")

    # Initialize the modern unified GenAI client
    client = genai.Client(api_key=api_key)

    # Convert pruned dataset into clean JSON string context
    context_str = json.dumps(pruned_payload, indent=2)
    
    # Generate the dynamic execution date
    current_date = datetime.now().strftime("%B %d, %Y")

    # Construct the user prompt with the requested format
    user_prompt = f"""
Execution Date: {current_date}
Analyze the following pruned competitor catalog data...
{context_str}
"""

    try:
        logger.info(f"Dispatching payload context ({len(context_str)} chars) to model '{model_name}'...")

        # Execute async call using client.aio
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,  # Low temperature for strict factual grounding
                top_p=0.95,
                # Suppress the AFC warning safely
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )

        if not response.text:
            logger.warning("Gemini API returned an empty text response.")
            return "Analysis generation failed: Empty response received from model."

        logger.info("Successfully generated competitive analysis brief.")
        return response.text

    except Exception as e:
        logger.error(f"Error invoking Gemini API in analyzer.py: {e}")
        raise RuntimeError(f"Gemini API invocation failed: {e}")
