import os, json, requests
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

@tool("canvas_courses", return_direct=False)
def canvas_courses() -> str:
    """
    Fetch all Canvas courses accessible to the user.
    Returns a summary list of course IDs and names. Canvas Token and Canvas Base URL are saved in .env and will be called.
    """
    base = os.getenv("CANVAS_BASE_URL")
    token = os.getenv("CANVAS_TOKEN")

    if not (base and token):
        return json.dumps({"error": "Missing Canvas credentials"})

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base}/api/v1/courses?enrollment_state=active"

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, list):
            return json.dumps({"error": "Unexpected Canvas response", "details": data})

        # Extract just what we need
        courses = [{"id": c.get("id"), "name": c.get("name")} for c in data]

        # Return a nice readable text summary + JSON for structured access
        summary_lines = [
            f"📘 {c['name']} (Course ID: {c['id']})"
            for c in courses if c.get("id") and c.get("name")
        ]

        return json.dumps({
            "summary": "\n".join(summary_lines),
            "courses": courses
        }, ensure_ascii=False, indent=2)

    except requests.RequestException as e:
        return json.dumps({"error": str(e)})