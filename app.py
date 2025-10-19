# app.py (OpenAI tools-agent + ElevenLabs voice/type toggle UI)
import os, json, traceback, warnings, base64, re, requests
from dotenv import load_dotenv, find_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

warnings.filterwarnings("ignore", message="API key must be provided when using hosted LangSmith API")
load_dotenv(find_dotenv(filename=".env", usecwd=True), override=True)

# ---- LangChain ----
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# ---- Tools ----
from tools import TOOLS  # expects tools/__init__.py exporting TOOLS

# ---- ElevenLabs ----
import requests

ELEVEN_API_KEY   = os.getenv("ELEVEN_API_KEY")
ELEVEN_VOICE_ID  = os.getenv("ELEVEN_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVEN_TTS_MODEL = os.getenv("ELEVEN_TTS_MODEL", "eleven_multilingual_v2")
ELEVEN_STT_URL   = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVEN_TTS_URL   = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}/stream"

# ---------------- Flask ----------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# ---------------- LLM config (OpenAI) ----------------
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # None uses official api
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
MODEL_NAME      = os.getenv("MODEL_NAME", "gpt-4o-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in your environment/.env")

llm = ChatOpenAI(
    model=MODEL_NAME,
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,   # None -> official OpenAI
    temperature=0.2,
    max_tokens=300,
    timeout=20,
)

print(f"🔧 Using model={MODEL_NAME} @ {OPENAI_BASE_URL or 'https://api.openai.com/v1'}")

SYSTEM = (
    "You are an accessibility education assistant for blind/low-vision students. "
    "Call tools when useful. Keep answers concise, direct, and screen-reader friendly."
)

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, tools=TOOLS, prompt=prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=TOOLS,
    verbose=False,
    handle_parsing_errors=True,
    max_iterations=4,
)

# ---------------- Helpers ----------------
def tts_b64(text: str) -> str | None:
    """Return base64 mp3 from ElevenLabs (or None on failure)."""
    if not (ELEVEN_API_KEY and text.strip()):
        return None
    try:
        r = requests.post(
            ELEVEN_TTS_URL,
            headers={"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={"text": text.strip(), "model_id": ELEVEN_TTS_MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            stream=True, timeout=60,
        )
        r.raise_for_status()
        audio_bytes = b"".join(r.iter_content(4096))
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception:
        return None
    
def _file_to_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = path.lower().split(".")[-1]
    mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "application/octet-stream")
    return f"data:{mime};base64,{b64}"

def _inline_local_image_paths(user_input: str) -> str:
    candidates = re.findall(r'((?:\S*/)?\S+\.(?:png|jpg|jpeg|gif|bmp|webp))', user_input, flags=re.IGNORECASE)
    inlined = user_input
    for p in set(candidates):
        if os.path.isfile(p):
            try:
                data_url = _file_to_data_url(p)
                inlined = inlined.replace(p, f'{p} [data_url:{data_url}]', 1)
            except Exception:
                pass
    return inlined

def _ensure_text(v: str, fallback: str = "") -> str:
    v = (v or "").strip()
    return v if v else fallback

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"ok": True})

# ---- Simple LLM ping
@app.post("/api/llm-test")
def llm_test():
    try:
        data = request.get_json(force=True)
        text = (data.get("text") or "Say hello in one short sentence.").strip()
        resp = llm.invoke([{"role": "user", "content": text}])
        return jsonify({"content": resp.content})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---- Agent (type mode)
@app.post("/api/agent")
def agent_route():
    try:
        data = request.get_json(force=True) if request.data else {}
        user_input = (data.get("input") or "").strip()
        extra_ctx  = (data.get("context") or "").strip()
        if not user_input:
            return jsonify({"error": "No input"}), 400

        preamble = (
            "Assist a blind/low-vision student with Canvas and course materials. "
            "Use OCR/Canvas/Semantic Scholar tools when helpful and keep responses concise."
        )

        user_input_inlined = _inline_local_image_paths(user_input)
        composed_input = f"{preamble}\n\n{extra_ctx}\n\nUser: {user_input_inlined}".strip()

        result = agent_executor.invoke({"input": composed_input})

        steps = []
        for step in result.get("intermediate_steps", []):
            tool_name = getattr(step[0], "name", str(step[0]))
            tool_input = step[1]
            observation = step[2] if len(step) > 2 else ""
            def _truncate(v):
                try:
                    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                except Exception:
                    s = str(v)
                return s[:2000]
            steps.append({
                "tool": tool_name,
                "tool_input": _truncate(tool_input),
                "observation": _truncate(observation),
            })

        return jsonify({"output": result.get("output"), "intermediate_steps": steps})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---- ElevenLabs: TTS (text -> base64 mp3)
@app.post("/tts")
def tts():
    if not ELEVEN_API_KEY:
        return jsonify({"ok": False, "error": "ELEVENLABS_API_KEY not set"}), 500
    try:
        data = request.get_json(force=True)
        text = _ensure_text(data.get("text"), "Hello. I am ready.")
        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": ELEVEN_TTS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        r = requests.post(ELEVEN_TTS_URL, headers=headers, json=payload, stream=True, timeout=60)
        r.raise_for_status()
        audio_bytes = b"".join(r.iter_content(chunk_size=4096))
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return jsonify({"ok": True, "audio_b64": audio_b64, "voice_id": ELEVEN_VOICE_ID, "model": ELEVEN_TTS_MODEL})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- ElevenLabs: STT (audio -> text)
@app.post("/stt")
def stt():
    if not ELEVEN_API_KEY:
        return jsonify({"ok": False, "error": "ELEVENLABS_API_KEY not set"}), 500
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No audio file uploaded"}), 400
    try:
        f = request.files["audio"]
        files = {"file": (f.filename or "audio.webm", f.read(), f.mimetype or "application/octet-stream")}
        data = {"model_id": "scribe_v1"}
        headers = {"xi-api-key": ELEVEN_API_KEY}
        r = requests.post(ELEVEN_STT_URL, headers=headers, files=files, data=data, timeout=120)
        r.raise_for_status()
        j = r.json()
        text = j.get("text") or j.get("transcript") or ""
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- VOICE: STT -> /api/agent -> TTS (single call for the UI)
@app.post("/voice")
def voice():
    if not ELEVEN_API_KEY:
        return jsonify({"ok": False, "error": "ELEVENLABS_API_KEY not set"}), 500
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No audio file uploaded"}), 400
    try:
        # 1) STT
        f = request.files["audio"]
        files = {"file": (f.filename or "audio.webm", f.read(), f.mimetype or "application/octet-stream")}
        headers = {"xi-api-key": ELEVEN_API_KEY}
        stt_resp = requests.post(ELEVEN_STT_URL, headers=headers, files=files, data={"model_id": "scribe_v1"}, timeout=120)
        stt_resp.raise_for_status()
        stt_json = stt_resp.json()
        transcript = stt_json.get("text") or stt_json.get("transcript") or ""

        # 2) Agent
        user_input_inlined = _inline_local_image_paths(transcript)
        composed_input = (
            "Assist a blind/low-vision student with Canvas and course materials. "
            "Use OCR/Canvas/Semantic Scholar tools when helpful and keep responses concise.\n\n"
            f"User: {user_input_inlined}"
        ).strip()
        result = agent_executor.invoke({"input": composed_input})
        reply = result.get("output") or "I didn’t find anything concrete."

        # 3) TTS
        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {"text": reply, "model_id": ELEVEN_TTS_MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        tts_resp = requests.post(ELEVEN_TTS_URL, headers=headers, json=payload, stream=True, timeout=60)
        tts_resp.raise_for_status()
        audio_bytes = b"".join(tts_resp.iter_content(chunk_size=4096))
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        return jsonify({"ok": True, "transcript": transcript, "reply": reply, "audio_b64": audio_b64})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- Helper: image upload to data URL
@app.post("/api/upload-image")
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "file missing"}), 400
    raw = request.files["file"].read()
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")
    return jsonify({"data_url": data_url})

# (Optional) login/signup passthroughs you already had:
@app.post("/api/login")
def login_route():
    from tools.auth_tool import auth_login
    data = request.get_json()
    ip = request.headers.get("X-Forwarded-For") or request.remote_addr
    ua = request.headers.get("User-Agent")
    res = json.loads(auth_login.run({
        "email": data["email"],
        "password": data["password"],
        "ip": ip,
        "user_agent": ua
    }))
    return jsonify(res), 200 if res.get("ok") else 401

@app.post("/api/signup")
def api_signup():
    from tools.signup_tool import auth_signup
    data = request.get_json(force=True)
    res = json.loads(auth_signup.run({
        "email": data.get("email",""),
        "password": data.get("password",""),
        "role": data.get("role","student"),
        "profile": data.get("profile")
    }))
    return jsonify(res), 200 if res.get("ok") else 400



@app.post("/ask")
def ask():
    """Body: { text: str, conv_id?: str }  ->  { ok, agent:{ok,content}, agent_audio_b64? }"""
    try:
        data = request.get_json(force=True)
        user_text = (data.get("text") or "").strip()
        if not user_text:
            return jsonify({"ok": False, "error": "Empty text"}), 400

        # Short preamble keeps tokens low
        preamble = (
            "Assist a blind/low-vision student with Canvas and course materials. "
            "Use OCR/Canvas/Semantic Scholar tools when helpful and keep responses concise."
        )
        composed_input = f"{preamble}\n\nUser: {user_text}".strip()

        result = agent_executor.invoke({"input": composed_input})
        reply  = (result.get("output") or "").strip()

        payload = {"ok": True, "agent": {"ok": True, "content": reply}}
        # Auto TTS (optional; comment out if you don't want speech in Type mode)
        b64 = tts_b64(reply)
        if b64:
            payload["agent_audio_b64"] = b64
        return jsonify(payload)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    


@app.post("/transcribe_and_run")
def transcribe_and_run():
    """FormData: audio=<file>, conv_id? -> { ok, transcript, agent:{ok,content}, agent_audio_b64? }"""
    if not ELEVEN_API_KEY:
        return jsonify({"ok": False, "error": "ELEVENLABS_API_KEY not set"}), 500
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No audio file uploaded"}), 400
    try:
        # 1) STT
        f = request.files["audio"]
        files = {"file": (f.filename or "audio.webm", f.read(), f.mimetype or "application/octet-stream")}
        stt = requests.post(ELEVEN_STT_URL, headers={"xi-api-key": ELEVEN_API_KEY}, files=files, data={"model_id": "scribe_v1"}, timeout=120)
        stt.raise_for_status()
        stt_json   = stt.json()
        transcript = (stt_json.get("text") or stt_json.get("transcript") or "").strip()

        # 2) Agent
        preamble = (
            "Assist a blind/low-vision student with Canvas and course materials. "
            "Use OCR/Canvas/Semantic Scholar tools when helpful and keep responses concise."
        )
        composed_input = f"{preamble}\n\nUser: {transcript}".strip()
        result = agent_executor.invoke({"input": composed_input})
        reply  = (result.get("output") or "I didn’t find anything concrete.").strip()

        # 3) TTS
        audio_b64 = tts_b64(reply)

        return jsonify({
            "ok": True,
            "transcript": transcript,
            "agent": {"ok": True, "content": reply},
            "agent_audio_b64": audio_b64,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)