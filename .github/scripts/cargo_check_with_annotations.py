"""ci-helper: 运行 cargo check，写日志，输出 ::error annotation 到 stdout。"""
import subprocess, sys, os

log_path = os.path.join(os.environ.get("WORKSPACE", "."), "rust-check.log")
summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

# 运行 cargo check，捕获 stdout/stderr
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
    # 逐行输出到 stdout（GitHub workflow command 从这里读取）
    print(line, flush=True)

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
        # 匹配 cargo 错误输出特征
        is_err = (
            "error[" in low           # error[E0xxx]
            or "error:" in low         # "error: ..."
            or "--> " in line          # --> file.rs:123
            or line.startswith("error")  # 行首 error
        )
        if is_err and line not in seen:
            seen.add(line)
            # 用最简单格式：::error title=...::message
            # 不指定 file/line，避免格式错误被忽略
            title = "cargo-error"
            msg = line[:255]  # 限制长度
            ann = f"::error title={title}::{msg}"
            print(ann, flush=True)

sys.exit(rc)
