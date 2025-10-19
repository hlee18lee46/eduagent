import os, json, requests
from langchain.tools import tool
from dotenv import load_dotenv
load_dotenv()

@tool("canvas_assignments", return_direct=False)
def canvas_assignments(course_id: str) -> str:
    """Fetch assignments from a Canvas LMS course."""
    base = os.getenv("CANVAS_BASE_URL")
    token = os.getenv("CANVAS_TOKEN")
    if not (base and token):
        return json.dumps({"error":"Missing Canvas credentials"})
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base}/api/v1/courses/{course_id}/assignments"
    r = requests.get(url, headers=headers, timeout=30)
    return r.text