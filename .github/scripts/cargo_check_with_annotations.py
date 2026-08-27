"""ci-helper: 运行 cargo check，写日志，输出所有含 error 的行作为 annotation。"""
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
    print(line, flush=True)

proc.wait()
rc = proc.returncode

# 写文件
with open(log_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# 写 step summary
if summary_path:
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

# cargo 失败时，把所有含 error 的行发 annotation
if rc != 0:
    seen = set()
    for line in lines:
        low = line.lower()
        # 匹配各种 error 格式
        if "error" in low and line not in seen:
            seen.add(line)
            safe = line[:500]
            print(f"::error::{line}", flush=True)

sys.exit(rc)
