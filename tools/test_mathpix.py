import base64, json
from dotenv import load_dotenv
from mathpix_tool import mathpix_ocr  # ⬅️ replace with the actual filename

load_dotenv()

# 1️⃣ Read the image and convert it to base64 data URL
with open("test1.png", "rb") as f:
    image_base64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()

# 2️⃣ Run the tool
result = mathpix_ocr(image_base64)

# 3️⃣ Parse and print the result nicely
try:
    data = json.loads(result)
    print("\n🧠 OCR Output:")
    print(json.dumps(data, indent=2))
    print("\n✅ LaTeX:", data.get("latex_styled"))
    print("✅ Plain text:", data.get("text"))
except json.JSONDecodeError:
    print("Raw result:", result)
