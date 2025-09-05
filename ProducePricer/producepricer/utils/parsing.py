import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from producepricer.utils.ai_utils import get_ai_response

# The schema for the JSON data we want from the AI
SCHEMA = {
    "type": "object",
    "properties": {
        "effective_date": {"type": "string", "description": "Date like YYYY-MM-DD"},
        "vendor": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Canonical item name (e.g., 'Onions, Jumbo Yellow')"},
                    "package": {"type": "string", "description": "Pack/size text (e.g., '50#', '12/1 PINT')"},
                    "unit": {"type": "string", "description": "Unit of sale (e.g., 'CS', 'LB', 'EA')"},
                    "price_usd": {"type": "number", "description": "Dollar amount per unit"},
                    "notes": {"type": "string"}
                },
                "required": ["name", "price_usd"]
            }
        }
    },
    "required": ["items"]
}

# The instructions for the AI model
SYSTEM_PROMPT = (
    "You convert semi-structured produce price lists into clean JSON. "
    "Extract an 'effective_date' from the header if present. "
    "Normalize item names by removing trailing pack/size descriptors. "
    "Return 'unit' as the price unit token (e.g., CS) if present; else leave blank."
)

USER_PROMPT_TEMPLATE = """PRICE LIST TEXT:

{pdf_text}

---
Return ONLY JSON that matches the provided schema. Infer:
- vendor from any header line (e.g., 'SENN BROTHERS PRODUCE').
- effective_date from text like 'Effective: 08/18/2025' (use YYYY-MM-DD).
- items: split each line into name, package (e.g., '50#', '12/.5 pt', '25#'), unit (e.g., 'CS'), and price_usd.
"""

def parse_price_list_with_openai(pdf_text: str) -> Dict[str, Any]:
    """Sends PDF text to OpenAI and returns structured JSON."""

    MAX_TEXT_LENGTH = 6000

    if len(pdf_text) > MAX_TEXT_LENGTH:
        pdf_text = pdf_text[:MAX_TEXT_LENGTH] + "\n[Text truncated due to length...]"

    # Clean and normalize the text for faster parsing
    cleaned_text = pdf_text.replace('\n\n', '\n').strip()

    try:
        response = get_ai_response(
            prompt="I am going to give you a text that i would like you to parse into structured JSON.",
            model="gpt-4-turbo-preview",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an assistant that parses produce price lists into structured data. Extract only what's clearly visible."},
                {"role": "user", "content": f"Parse this price list into JSON format with vendor, effective_date, and items array with name and price_usd fields:\n\n{cleaned_text}"}
            ]
        )

        # FIX: Use the dict returned by get_ai_response
        if not response.get("success"):
            raise Exception(response.get("error", "Unknown error from AI"))
        content = response["content"]
        return json.loads(content)
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return {"error": str(e), "items": []}


def coerce_iso_date(s: Optional[str]) -> datetime.date:
    """Converts a date string to a date object, with fallbacks."""
    if not s:
        return datetime.utcnow().date()
    # Accept YYYY-MM-DD
    m1 = re.match(r"(\d{4})-(\d{2})-(\d{2})", s.strip())
    if m1:
        return datetime(int(m1.group(1)), int(m1.group(2)), int(m1.group(3))).date()
    # Accept MM/DD/YYYY
    m2 = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
    if m2:
        return datetime(int(m2.group(3)), int(m2.group(1)), int(m2.group(2))).date()
    
    return datetime.utcnow().date()