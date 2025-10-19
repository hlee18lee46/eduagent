# tools/canvas_course_tool_test.py
import json
import os
from dotenv import load_dotenv

# Ensure env vars are loaded even if test is run directly
load_dotenv()

# Import the tool (this path assumes you run from the repo root)
from canvas_course_tool import canvas_courses

def pretty_print(result_json: str):
    try:
        obj = json.loads(result_json)
    except json.JSONDecodeError:
        print(result_json)
        return

    if "error" in obj:
        print("❌ Error:", obj["error"])
        if "details" in obj:
            print("Details:", obj["details"])
        return

    print("\n=== Canvas Courses ===")
    print(obj.get("summary", "(no summary)"))
    print("\nRaw JSON:")
    print(json.dumps(obj, indent=2, ensure_ascii=False))

def main():
    # Show which endpoint we’re about to call for quick debugging
    print("CANVAS_BASE_URL:", os.getenv("CANVAS_BASE_URL"))
    print("CANVAS_TOKEN set:", bool(os.getenv("CANVAS_TOKEN")))

    # Prefer the LangChain wrapper:
    try:
        result = canvas_courses.invoke({})
    except TypeError:
        # Fallback to the underlying function if needed
        result = canvas_courses.func()

    pretty_print(result)

if __name__ == "__main__":
    main()
