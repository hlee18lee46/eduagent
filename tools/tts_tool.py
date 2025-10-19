import os, json, uuid, requests
from langchain.tools import tool
from dotenv import load_dotenv
load_dotenv()

STATIC_AUDIO = os.path.join(os.path.dirname(__file__), "..", "static", "audio")

@tool("tts", return_direct=True)
def tts(text: str) -> str:
    """Generate speech using ElevenLabs and return /static/audio/<file>.mp3."""
    api = os.getenv("ELEVEN_API_KEY")
    voice = os.getenv("ELEVEN_VOICE", "Rachel")
    if not api:
        return json.dumps({"error":"Missing ELEVEN_API_KEY"})

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?optimize_streaming_latency=2"
    headers = {"xi-api-key": api, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": "eleven_turbo_v2"}
    r = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
    fid = f"{uuid.uuid4().hex}.mp3"
    out_path = os.path.join(STATIC_AUDIO, fid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return json.dumps({"audio_url": f"/static/audio/{fid}"})