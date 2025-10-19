# app.py (OpenAI tools-agent, fast & reliable)
import os, json, traceback, warnings, base64, re
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

# ---------------- Flask ----------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ---------------- LLM config (OpenAI) ----------------
# Use OpenAI directly. If you want Azure/OpenRouter/etc, set OPENAI_BASE_URL in .env.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # None uses official api
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")   # your OpenAI key
MODEL_NAME      = os.getenv("MODEL_NAME", "gpt-4o-mini")  # good at tool-calling & fast

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in your environment/.env")

llm = ChatOpenAI(
    model=MODEL_NAME,
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,      # None -> official OpenAI
    temperature=0.2,
    max_tokens=300,
    timeout=20,                    # keep requests snappy
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

# Structured tool-calling agent (no brittle ReAct text parsing)
agent = create_openai_tools_agent(llm, tools=TOOLS, prompt=prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=TOOLS,
    verbose=False,
    handle_parsing_errors=True,
    max_iterations=4,  # bounds latency
)

# ---------------- Helpers ----------------
def _file_to_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    # naive mime guess; adjust if needed
    ext = path.lower().split(".")[-1]
    mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "application/octet-stream")
    return f"data:{mime};base64,{b64}"

def _inline_local_image_paths(user_input: str) -> str:
    """Find simple local image paths like tools/foo.png and inline as base64 to help the tool call."""
    # matches tokens that look like relative paths ending in image extensions
    candidates = re.findall(r'((?:\S*/)?\S+\.(?:png|jpg|jpeg|gif|bmp|webp))', user_input, flags=re.IGNORECASE)
    inlined = user_input
    for p in set(candidates):
        if os.path.isfile(p):
            try:
                data_url = _file_to_data_url(p)
                # replace the bare path with a short tag + data URL near it
                inlined = inlined.replace(p, f'{p} [data_url:{data_url}]', 1)
            except Exception:
                pass
    return inlined

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"ok": True})

# Quick sanity: call the LLM directly without Agent
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

@app.post("/api/agent")
def agent_route():
    """
    Body: { "input": "user message", "context": "optional context" }
    """
    try:
        data = request.get_json(force=True) if request.data else {}
        user_input = (data.get("input") or "").strip()
        extra_ctx  = (data.get("context") or "").strip()
        if not user_input:
            return jsonify({"error": "No input"}), 400

        # helpful preamble, but short (keeps token count low)
        preamble = (
            "Assist a blind/low-vision student with Canvas and course materials. "
            "Use OCR/Canvas/Semantic Scholar tools when helpful and keep responses concise."
        )

        # Inline any local image paths as data URLs so the model can pass them cleanly to mathpix_ocr
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

# Helper: create a data URL for Mathpix uploads
@app.post("/api/upload-image")
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "file missing"}), 400
    raw = request.files["file"].read()
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")
    return jsonify({"data_url": data_url})

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)