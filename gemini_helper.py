import os
from typing import Dict, Any, List
from dotenv import load_dotenv

# Ensure .env is loaded from project root
_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_ENV_PATH)

try:
    from google import genai
except Exception:
    genai = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()


def _build_prompt(product_data: Dict[str, Any], allowed_aspects: List[Dict[str, Any]]) -> str:
    """
    Build a concise instruction prompt to infer item specifics.
    allowed_aspects: list of aspect dicts from eBay taxonomy with fields:
      - localizedAspectName
      - aspectConstraint.aspectMode (e.g., FREE_TEXT or SELECTION_ONLY)
      - aspectValues.localizedValue (optional choices)
    """
    title = product_data.get("title") or product_data.get("Title") or ""
    brand = product_data.get("Brand") or product_data.get("brand") or ""
    details = product_data.get("prodDetails", {}) or {}
    overview = product_data.get("productOverview", {}) or {}
    description = product_data.get("description") or product_data.get("Description") or ""

    lines = [
        "You are assisting with eBay item specifics.",
        "Given product info, fill ONLY the aspects listed, using best inference.",
        "Follow rules:",
        "- Use exact values from the choices when provided (case-insensitive match).",
        "- If no exact match, pick the closest appropriate choice.",
        "- If FREE_TEXT, provide a short, clean value (no sentences).",
        "- If unknown, output an empty value.",
        "Return JSON mapping aspect name to value.",
        f"Title: {title}",
        f"Brand: {brand}",
        f"Description: {description[:600]}",
        "Details:",
    ]
    for k, v in details.items():
        lines.append(f"- {k}: {v}")
    lines.append("Overview:")
    for k, v in overview.items():
        lines.append(f"- {k}: {v}")

    lines.append("Aspects to fill:")
    for a in allowed_aspects:
        name = a.get("localizedAspectName")
        mode = (a.get("aspectConstraint", {}) or {}).get("aspectMode", "")
        values = [v.get("localizedValue") for v in a.get("aspectValues", [])] if a.get("aspectValues") else []
        if mode == "SELECTION_ONLY" and values:
            lines.append(f"- {name} (mode={mode}) choices: {', '.join(map(str, values))}")
        else:
            # For FREE_TEXT (and any other non-selection mode), do not send choices
            lines.append(f"- {name} (mode={mode})")
    return "\n".join(lines)


import json
import re
try:
    from google.genai.types import GenerateContentConfig  # optional; some versions may differ
except Exception:
    GenerateContentConfig = None


def suggest_item_specifics_with_gemini(product_data: Dict[str, Any], taxonomy_aspects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use Gemini to suggest values for item specifics constrained by taxonomy.
    """
    if not genai or not GEMINI_API_KEY:
        print("Error: Gemini API key or package missing.")
        return {}

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 1. Build the prompt (Reuse your existing _build_prompt function)
    prompt = _build_prompt(product_data, taxonomy_aspects)

    try:
        # Build kwargs for compatibility across library versions
        kwargs = {
            "model": GEMINI_MODEL,
            "contents": prompt,
        }
        if GenerateContentConfig is not None:
            kwargs["config"] = GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        resp = client.models.generate_content(**kwargs)

        # 3. Robust Text Extraction
        text = ""
        if hasattr(resp, "text") and resp.text:
            text = resp.text
        elif hasattr(resp, "output_text") and resp.output_text:
            text = resp.output_text
        elif hasattr(resp, "candidates") and resp.candidates:
            for cand in resp.candidates:
                content = getattr(cand, "content", None)
                if content and getattr(content, "parts", None):
                    for p in content.parts:
                        if hasattr(p, "text") and p.text:
                            text = p.text
                            break
                if text: break

        if not text:
            print("Warning: Gemini returned empty text.")
            return {}

        # 4. Clean Markdown (Strip ```json and ```)
        # Even in JSON mode, models sometimes wrap the output in markdown blocks.
        clean_text = re.sub(r"```json|```", "", text).strip()

        # 5. Parse JSON
        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error. Raw text received: {clean_text[:100]}...")
            return {}

        if not isinstance(parsed, dict):
            return {}

        # 6. Post-process: Validate against eBay choices
        result: Dict[str, Any] = {}
        for aspect in taxonomy_aspects:
            name = aspect.get("localizedAspectName")
            mode = (aspect.get("aspectConstraint", {}) or {}).get("aspectMode")
            options = [v.get("localizedValue") for v in aspect.get("aspectValues", [])] if aspect.get("aspectValues") else []

            val = parsed.get(name)
            if not val:
                continue

            sval = str(val).strip()

            # Logic: If the aspect is SELECTION_ONLY, we must match one of the provided options.
            if mode == "SELECTION_ONLY" and options:
                lower_map = {str(o).lower(): o for o in options}
                if sval.lower() in lower_map:
                    result[name] = lower_map[sval.lower()]
                else:
                    # If the model inferred a value but it's not in the allowed list,
                    # discard it rather than sending invalid data to eBay.
                    # Alternatively, you can fuzzy match here if you wish.
                    continue
            else:
                result[name] = sval

        return result

    except Exception as e:
        print(f"Gemini critical error: {e}")
        return {}
