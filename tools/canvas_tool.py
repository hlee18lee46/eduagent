import os, json, requests
from datetime import datetime, timezone
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

@tool("canvas_assignments", return_direct=False)
def canvas_assignments(course_id: str) -> str:
    """
    Fetch upcoming assignments from a Canvas LMS course.
    Only returns assignments with a due date in the future. When the course ID is not given, use the canvas_course_tool to get the course IDs and then fetch assignments accordingly.
    """
    base = os.getenv("CANVAS_BASE_URL")
    token = os.getenv("CANVAS_TOKEN")

    if not (base and token):
        return json.dumps({"error": "Missing Canvas credentials"})

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{base}/api/v1/courses/{course_id}/assignments?per_page=100"

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        assignments = r.json()

        now = datetime.now(timezone.utc)
        upcoming = []

        for a in assignments:
            due_str = a.get("due_at")
            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                    if due_dt > now:
                        upcoming.append({
                            "id": a.get("id"),
                            "name": a.get("name"),
                            "due_at": due_dt.isoformat(),
                            "html_url": a.get("html_url"),
                        })
                except ValueError:
                    # Skip invalid date format
                    pass

        summary_lines = [
            f"📅 {a['name']} — due {a['due_at']} ({a['html_url']})"
            for a in sorted(upcoming, key=lambda x: x["due_at"])
        ]

        return json.dumps({
            "course_id": course_id,
            "count": len(upcoming),
            "summary": "\n".join(summary_lines) if upcoming else "No upcoming assignments found.",
            "assignments": upcoming
        }, ensure_ascii=False, indent=2)

    except requests.RequestException as e:
        return json.dumps({"error": str(e)})
