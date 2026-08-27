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

# cargo 失败时，把所有含 error 的行发 annotation（用原始 bytes 输出）
if rc != 0:
    seen = set()
    for line in lines:
        low = line.lower()
        if "error" in low and line not in seen:
            seen.add(line)
            # 用原始 bytes 写 stdout，确保 GitHub 识别
            ann = f"::error::{line}\n"
            sys.stdout.buffer.write(ann.encode("utf-8"))
            sys.stdout.flush()

sys.exit(rc)
