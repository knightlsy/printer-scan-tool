"""ci-helper: 运行 cargo check，写日志，输出 ::error annotation 到 stdout。"""
import subprocess, sys, os

log_path = os.path.join(os.environ.get("WORKSPACE", "."), "rust-check.log")
summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

# 运行 cargo check（二进制模式，手动 utf-8 解码，避免 Windows cp1252 处理中文报错崩溃）
proc = subprocess.Popen(
    ["cargo", "check"],
    cwd="src-tauri",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
)

lines = []
for raw in proc.stdout:
    line = raw.decode("utf-8", errors="replace").rstrip("\n")
    lines.append(line)
    # 写入 stdout（GitHub workflow command 从这里读取；用 bytes 避免 Windows cp1252 编码报错）
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

proc.wait()
rc = proc.returncode

# 写文件日志
with open(log_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# 写 step summary（便于网页查看）
if summary_path:
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n## Rust 编译诊断\n\n```\n")
        f.write("\n".join(lines) + "\n")
        f.write("```\n\n")

# cargo 失败时，把关键错误行输出为 ::error annotation
if rc != 0:
    seen = set()
    for line in lines:
        low = line.lower()
        is_err = (
            "error[" in low
            or "error:" in low
            or "--> " in line
            or line.startswith("error")
        )
        if is_err and line not in seen:
            seen.add(line)
            title = "cargo-error"
            msg = line[:255]
            ann = f"::error title={title}::{msg}\n"
            sys.stdout.buffer.write(ann.encode("utf-8"))
            sys.stdout.buffer.flush()

sys.exit(rc)
