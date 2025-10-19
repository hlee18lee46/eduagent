# test_mca.py
import json
from llvm_mca_tool import llvm_mca_report

# 🧩 Example AArch64 assembly snippet
asm_code = """
// Simple add test
add x0, x1, x2
ret
"""

# 🧠 Call the tool directly
result_json = llvm_mca_report.func(code=asm_code, is_asm=True, cpu="apple-m2")

# Parse the JSON result
result = json.loads(result_json)

print("\n=== LLVM-MCA RESULT ===")
if not result.get("ok"):
    print("❌ Error:", result.get("error"))
else:
    print(f"✅ CPU: {result['cpu']}")
    print("\n📊 Summary:")
    for line in result["summary"]:
        print("  ", line)
    print("\n📁 Output files:")
    print("  Report:", result["report_path"])
    print("  Timeline:", result["timeline_path"])
    print("  Markdown:", result["markdown_path"])
    print()

