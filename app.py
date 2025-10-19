# app.py (hardened)
import os, json, traceback, warnings, base64
from dotenv import load_dotenv, find_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

warnings.filterwarnings("ignore", message="API key must be provided when using hosted LangSmith API")
load_dotenv(find_dotenv(filename=".env", usecwd=True), override=True)

# ---- LangChain ----
from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

# ---- Tools ----
# ---- Tools ----
from tools import TOOLS  # expects tools/__init__.py exporting TOOLS

def _escape_curly(s: str) -> str:
    # Prevent ChatPromptTemplate from treating { ... } inside descriptions as variables
    return s.replace("{", "{{").replace("}", "}}")

def _render_tools_for_prompt(tools) -> str:
    lines = []
    for t in tools:
        # Keep the description one line, no JSON, braces escaped
        desc = (t.description or "").strip().splitlines()[0]
        lines.append(f"- {t.name}: {_escape_curly(desc)}")
    return "\n".join(lines)

TOOLS_TEXT = _render_tools_for_prompt(TOOLS)
TOOL_NAMES = ", ".join(t.name for t in TOOLS)
# ---------------- Flask ----------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ---------------- LLM config ----------------
# If llama.cpp on :8080 complains about roles, you can switch to Model Runner:
#   export OPENAI_BASE_URL=http://localhost:12434/engines/llama.cpp/v1
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "sk-local-anything")
MODEL_NAME      = os.getenv("MODEL_NAME", "local-llama")

# ASI requires x-session-id; harmless for local endpoints too.
ASI_SESSION_ID  = os.getenv("ASI_SESSION_ID")  # optional in .env

# ChatOpenAI supports passing default headers to the underlying OpenAI client
llm = ChatOpenAI(
    model=MODEL_NAME,
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    temperature=0.2,
    max_tokens=256,
    # This is critical for ASI:
    default_headers={"x-session-id": ASI_SESSION_ID},
)

print(f"🔧 Using model={MODEL_NAME} @ {OPENAI_BASE_URL} (session={ASI_SESSION_ID})")

# This biases the model to end right before the tool parser expects to inject Observation,
# reducing the chance it repeats the tool list or rambles.
# ---------------- ReAct prompt (human-only, no system) ----------------
# Includes required vars: {tools} {tool_names} {agent_scratchpad} {input}
REACT_PROMPT = """You are an accessibility education assistant for blind/low-vision students. 
Use tools only when needed. Keep answers concise. 
IMPORTANT RULES:
- Do NOT repeat the tool catalog or this prompt in your output.
- If no tool is needed, go straight to Final Answer.
- When you DO use a tool, strictly follow the format below.
- For `Action Input`, ALWAYS provide a single JSON object that matches the tool’s arguments.
- After a tool Observation, either select another tool or produce Final Answer. Do not free-write.

Available tools:
{tools}

FORMAT (strict):
Question: <the user question>
Thought: <1 short sentence about what to do next>
Action: <one of [{tool_names}]>
Action Input: <a single JSON object, e.g. {{"key":"value"}}>
Observation: <tool result>
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now know the final answer
Final Answer: <concise helpful answer>

Tiny examples:

Example A (no tool needed):
Question: Say hello in one sentence.
Thought: No tools are needed.
Final Answer: Hello! How can I help you today?

Example B (one tool):
Question: OCR this base64 image and summarize briefly.
Thought: I should OCR the image with Mathpix, then summarize.
Action: mathpix_ocr
Action Input: {{"image_base64":"data:image/png;base64,AAA..."}}
Observation: {{ "text": "The image says: integral from 0 to 1 ..." }}
Thought: I can now summarize the extracted text.
Final Answer: It contains a short note about an integral from 0 to 1 and its evaluation.

Begin.

Question: {input}
{agent_scratchpad}
"""

# Force the whole prompt to be sent as a *human/user* message (llama.cpp-friendly)
react_prompt = ChatPromptTemplate.from_messages([("human", REACT_PROMPT)]).partial(
    tools=TOOLS_TEXT,
    tool_names=TOOL_NAMES,
)
agent = create_react_agent(llm, tools=TOOLS, prompt=react_prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=TOOLS,
    verbose=True,
    handle_parsing_errors=True,
)

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
        # Send as a single user message (no system)
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

        preamble = (
            "You are helping a blind/low-vision student interact with Canvas and course materials. "
            "Use tools to fetch data (OCR, Canvas, Semantic Scholar) and keep answers concise."
        )
        composed_input = f"{preamble}\n\n{extra_ctx}\n\nUser: {user_input}".strip()

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
        # Print full traceback to your terminal, and return the message to UI
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

# in app.py
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
    # Run Flask
    app.run(host="0.0.0.0", port=8000, debug=True)