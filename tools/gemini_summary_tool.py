import os
import json
from typing import Optional, Literal, Any, Dict, List

from dotenv import load_dotenv
load_dotenv()

from langchain.tools import tool

# Google GenAI (Gemini) SDK
# pip install google-genai
import google.genai as genai
from google.genai import types


def _extract_text_from_mathpix(maybe_json: str) -> str:
    """
    If the input looks like Mathpix OCR JSON, extract best-available text.
    Otherwise return the string unchanged.
    """
    try:
        obj = json.loads(maybe_json)
    except Exception:
        return maybe_json  # not JSON -> assume it's already plain text

    # Mathpix variants to consider
    candidates: List[str] = []
    for k in ("text", "plaintext", "latex_styled", "latex", "asciimath"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    # Some Mathpix responses put OCR in "data" array with "value"/"text"
    if not candidates and isinstance(obj.get("data"), list):
        for item in obj["data"]:
            for k in ("text", "value"):
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    candidates.append(v.strip())

    # Join/return best
    if candidates:
        # Prefer normal text if present, else first candidate
        for pref in ("text", "plaintext"):
            if pref in obj and isinstance(obj[pref], str) and obj[pref].strip():
                return obj[pref].strip()
        return "\n".join(candidates)

    # Fallback to original string form if nothing was useful
    return maybe_json


def _build_summary_prompt(
    text: str,
    style: Literal["paragraph", "bullets"] = "paragraph",
    simplify_for_accessibility: bool = True,
    voice: Literal["neutral", "teacher"] = "teacher",
    max_words: int = 150,
) -> str:
    bullets_hint = (
        "Provide 3–6 concise bullet points with line breaks. "
        "Start each item with a dash or bullet character."
        if style == "bullets"
        else "Provide 1 short paragraph."
    )
    access_hint = (
        "Write clearly for blind/low-vision learners using a screen reader. "
        "Avoid dense math unless necessary; expand abbreviations; define symbols briefly."
        if simplify_for_accessibility
        else "Assume the reader is comfortable with technical terms."
    )
    voice_hint = "Use a friendly tutor tone." if voice == "teacher" else "Use a neutral, concise tone."

    return (
        f"{voice_hint} {access_hint} {bullets_hint} "
        f"Limit to about {max_words} words.\n\n"
        f"Text to summarize:\n{text}"
    )


@tool("gemini_summary", return_direct=False)
def gemini_summary(
    content: str,
    style: Literal["paragraph", "bullets"] = "paragraph",
    json_mode: bool = False,
    simplify_for_accessibility: bool = True,
    voice: Literal["neutral", "teacher"] = "teacher",
    max_words: int = 150,
    image_data_url: Optional[str] = None,
    model: str = "gemini-2.0-flash",  # fast + capable; use -pro for higher quality
) -> str:
    """
    Summarize text (or Mathpix OCR JSON) with Google Gemini.
    Optionally include an image data URL (data:image/...;base64,AAAA).

    Args:
        content: Plain text OR Mathpix OCR JSON string. Auto-extracts text if JSON.
        style: "paragraph" or "bullets"
        json_mode: If True, returns structured JSON (summary, key_points, actions, reading_level).
        simplify_for_accessibility: Optimize for screen readers and clarity.
        voice: "neutral" or "teacher" tone.
        max_words: Target maximum words for summary.
        image_data_url: Optional data URL of an image to co-summarize.
        model: Gemini model name (e.g., "gemini-2.0-flash", "gemini-2.0-pro").

    Returns:
        str containing either natural-language summary or JSON string.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"error": "Missing GEMINI_API_KEY in environment."})

    client = genai.Client(api_key=api_key)

    # If input looks like Mathpix JSON, extract its text
    text = _extract_text_from_mathpix(content)
    prompt = _build_summary_prompt(
        text=text,
        style=style,
        simplify_for_accessibility=simplify_for_accessibility,
        voice=voice,
        max_words=max_words,
    )

    # Build input parts
    parts: list[Any] = [prompt]
    # If you want to support image summarization jointly:
    if image_data_url and image_data_url.startswith("data:"):
        parts = [types.Part.from_dict({"mime_type": "text/plain", "data": prompt}), image_data_url]

    # JSON response schema (agent-friendly)
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "summary": types.Schema(type=types.Type.STRING),
            "key_points": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
            "actions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
            "reading_level": types.Schema(type=types.Type.STRING),
        },
        required=["summary"],
    )

    try:
        if json_mode:
            resp = client.models.generate_content(
                model=model,
                contents=parts,
                generation_config=types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            # Ensure valid JSON
            return resp.text
        else:
            resp = client.models.generate_content(model=model, contents=parts)
            return resp.text
    except Exception as e:
        return json.dumps({"error": str(e)})