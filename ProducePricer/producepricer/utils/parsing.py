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

    MAX_TEXT_LENGTH = 4000  # Reduced to prevent token limit issues

    if len(pdf_text) > MAX_TEXT_LENGTH:
        pdf_text = pdf_text[:MAX_TEXT_LENGTH] + "\n[Text truncated due to length...]"

    # Clean and normalize the text for faster parsing
    # Remove problematic characters that could break JSON
    cleaned_text = pdf_text.replace('\n\n', '\n').strip()
    # Escape any existing quotes and backslashes that could break JSON
    cleaned_text = cleaned_text.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\t', '\\t')
    # Remove or replace control characters
    cleaned_text = ''.join(char for char in cleaned_text if ord(char) >= 32 or char in '\n\t')

    # First attempt with full text
    result = _attempt_parse(cleaned_text)
    
    # If we got a truncation error, try with smaller chunks
    if "error" in result and "truncated" in result.get("error", "").lower():
        print("Attempting with smaller text chunk due to truncation...")
        smaller_text = cleaned_text[:2000] + "\n[Text further truncated...]"
        result = _attempt_parse(smaller_text)
    
    return result

def _attempt_parse(cleaned_text: str) -> Dict[str, Any]:
    """Helper function to attempt parsing with given text."""
    try:
        response = get_ai_response(
            prompt="I am going to give you a text that i would like you to parse into structured JSON.",
            model="gpt-4-turbo-preview",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an assistant that parses produce price lists into structured data. Extract only what's clearly visible. Always return complete, valid JSON. If the list is very long, prioritize the first items and ensure the JSON structure is properly closed."},
                {"role": "user", "content": f"Parse this price list into JSON format with vendor, effective_date, and items array with name and price_usd fields. IMPORTANT: Always ensure the JSON is complete and properly closed, even if you need to limit the number of items:\n\n{cleaned_text}"}
            ]
        )

        # FIX: Use the dict returned by get_ai_response
        if not response.get("success"):
            raise Exception(response.get("error", "Unknown error from AI"))
        content = response["content"]
        
        # Additional validation: check if content is valid JSON before parsing
        if not content or not content.strip():
            raise Exception("Empty response from AI")
            
        # Try to parse JSON and handle potential parsing errors
        try:
            parsed_json = json.loads(content)
            return parsed_json
        except json.JSONDecodeError as json_err:
            print(f"JSON parsing error: {json_err}")
            print(f"Raw AI response: {content[:500]}...")  # Show first 500 chars for debugging
            
            # Try to fix common JSON issues including truncated responses
            try:
                fixed_content = content.strip()
                
                # Handle truncated responses - try to close incomplete JSON structures
                if not fixed_content.endswith('}'):
                    # Count open braces and brackets to try to close them properly
                    open_braces = fixed_content.count('{') - fixed_content.count('}')
                    open_brackets = fixed_content.count('[') - fixed_content.count(']')
                    
                    # Remove any incomplete item at the end
                    last_complete_item = fixed_content.rfind('},')
                    if last_complete_item > 0:
                        fixed_content = fixed_content[:last_complete_item + 1]
                    
                    # Close any incomplete objects/arrays
                    for _ in range(open_brackets):
                        fixed_content += ']'
                    for _ in range(open_braces):
                        fixed_content += '}'
                
                # Remove trailing commas
                fixed_content = re.sub(r',\s*([}\]])', r'\1', fixed_content)
                
                parsed_json = json.loads(fixed_content)
                print(f"Successfully recovered truncated JSON with {len(parsed_json.get('items', []))} items")
                return parsed_json
                
            except Exception as fix_err:
                print(f"Could not fix JSON: {fix_err}")
                # If we can't fix it, return a minimal valid structure with error info
                return {
                    "error": f"Truncated or malformed JSON response: {json_err}",
                    "items": [],
                    "vendor": "Unknown",
                    "effective_date": None
                }
                
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