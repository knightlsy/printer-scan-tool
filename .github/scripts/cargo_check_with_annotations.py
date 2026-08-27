"""ci-helper: 运行 cargo check，写日志，输出 ::error annotation。"""
import subprocess, sys, os

log_path = os.path.join(os.environ.get("WORKSPACE", "."), "rust-check.log")
summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

proc = subprocess.Popen(
    ["cargo", "check"],
    cwd="src-tauri",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

lines = []
for line in proc.stdout:
    line = line.rstrip("\n")
    lines.append(line)
    print(line)
    low = line.lower()
    if "error[" in low or "error:" in low or "--->" in low:
        safe = line[:500]
        print(f"::error::{safe}")

proc.wait()
rc = proc.returncode

# 写文件
with open(log_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# 写 step summary
if summary_path:
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

sys.exit(rc)
