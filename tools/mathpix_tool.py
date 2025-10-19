# tools/mathpix_tool.py
import os
import json
import base64
import mimetypes
import requests
from datetime import datetime
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

def save_text_to_file(text: str, prefix: str = "mathpix") -> str:
    """Save OCR text output into ./outputs/ folder."""
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join("outputs", f"{prefix}_{timestamp}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    return file_path

def _maybe_to_data_url(src: str) -> str:
    """
    If `src` is already a data URL, return it.
    Otherwise, treat it as a local file path (relative or absolute), read it,
    and return a data URL like data:image/png;base64,<...>.
    Also tries 'tools/<src>' when the given relative path doesn't exist.
    """
    # Already a data URL?
    if isinstance(src, str) and src.strip().lower().startswith("data:"):
        return src

    # Resolve local path
    path = src.strip()
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        # try given relative path
        if not os.path.exists(path):
            # fall back to tools/<path>
            candidate = os.path.join("tools", path)
            if os.path.exists(candidate):
                path = candidate

    if not os.path.exists(path):
        raise FileNotFoundError(f"Image file not found: {src}")

    # Guess content type from file extension
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        # Default to image/png if unknown but common image types missed
        ext = os.path.splitext(path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }.get(ext, "application/octet-stream")

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

@tool("mathpix_ocr", return_direct=False)
def mathpix_ocr(image_base64_or_path: str) -> str:
    """
    OCR math or text from a base64 data URL **or a local file path** using Mathpix API.
    Returns JSON, and also saves plain text to a local file.
    """
    app_id  = os.getenv("MATHPIX_APP_ID")
    app_key = os.getenv("MATHPIX_APP_KEY")
    if not (app_id and app_key):
        return json.dumps({"error": "Missing Mathpix credentials"})

    try:
        src_data_url = _maybe_to_data_url(image_base64_or_path)
    except Exception as e:
        return json.dumps({"error": f"File handling error: {e}"})

    headers = {"app_id": app_id, "app_key": app_key, "Content-Type": "application/json"}
    payload = {
        "src": src_data_url,
        "formats": ["text", "latex_styled"],
        "data_options": {"include_asciimath": True, "include_latex": True}
    }

    try:
        r = requests.post("https://api.mathpix.com/v3/text", headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()

        # Extract best text candidate
        text = data.get("text") or data.get("plaintext") or ""
        if not text and isinstance(data.get("data"), list):
            for item in data["data"]:
                if isinstance(item, dict) and "value" in item:
                    text += str(item["value"]) + "\n"

        file_path = save_text_to_file(text or "[No text extracted]")
        data["saved_to"] = file_path
        return json.dumps(data, ensure_ascii=False)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Mathpix request failed: {e}"})