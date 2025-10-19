import os, subprocess, tempfile, json, shutil
from langchain.tools import tool

LLVM_MCA = shutil.which("llvm-mca") or "/opt/homebrew/opt/llvm/bin/llvm-mca"

def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    return p.stdout

@tool("llvm_mca_report", return_direct=False)
def llvm_mca_report(code: str, is_asm: bool = True, cpu: str = "apple-m2") -> str:
    """
    Run llvm-mca on a code snippet.
    - code: aarch64 asm (default) or C code if is_asm=False
    - cpu: apple-m2 or neoverse-v2
    Returns JSON with {summary, report_path, timeline_path, markdown_path}
    """
    if not os.path.exists(LLVM_MCA):
        return json.dumps({"ok": False, "error": f"llvm-mca not found at {LLVM_MCA}"})
    os.makedirs("reports", exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "snippet.s" if is_asm else "snippet.c")
        with open(src, "w") as f:
            f.write(code)

        asm_path = src
        if not is_asm:
            # compile C -> asm aarch64 (Apple target by default)
            asm_path = os.path.join(td, "snippet.s")
            cc = shutil.which("clang") or "clang"
            target = "aarch64-apple-darwin"
            cc_cmd = [cc, "-O3", "-S", "-target", target, src, "-o", asm_path]
            cc_out = _run(cc_cmd)
            if not os.path.exists(asm_path):
                return json.dumps({"ok": False, "error": "Failed to compile C to assembly", "compiler_output": cc_out})

        base = f"mca_{cpu}_{'asm' if is_asm else 'c'}"
        txt = os.path.join("reports", f"{base}.txt")
        tl  = os.path.join("reports", f"{base}.timeline.txt")
        md  = os.path.join("reports", f"{base}.md")

        rep = _run([LLVM_MCA, "-mtriple=aarch64", f"-mcpu={cpu}", asm_path])
        tlr = _run([LLVM_MCA, "-mtriple=aarch64", f"-mcpu={cpu}", "-timeline", asm_path])

        with open(txt, "w") as f: f.write(rep)
        with open(tl,  "w") as f: f.write(tlr)
        with open(md,  "w") as f:
            f.write(f"## llvm-mca report ({cpu})\n\n```text\n{rep}\n```\n\n### Timeline ({cpu})\n\n```text\n{tlr}\n```\n")

        # quick summary: pull a few key lines
        summary = []
        for line in rep.splitlines():
            if any(k in line for k in ["Iterations", "Instructions", "Total Cycles", "uOps Per Cycle", "IPC"]):
                summary.append(line.strip())

        return json.dumps({
            "ok": True,
            "cpu": cpu,
            "summary": summary,
            "report_path": txt,
            "timeline_path": tl,
            "markdown_path": md
        })