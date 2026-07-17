# 在线更新系统 · 使用说明

模式：**双源回退（LAN 优先 + Gitee 兜底）**。客户端只认「候选清单源列表」，
按顺序探测，首个成功即用；下载/校验/回滚与来源无关。

## 一、组成

```
scangate/updater/
├── settings.py        更新源与偏好（内置默认 + update_source.json + 用户覆盖文件）
├── manifest.py        版本比对 + 多源清单探测 fetch_manifest
├── download.py        Downloader：HTTP Range 续传 / SMB 分块续传 + SHA256 校验
├── install.py         备份 .bak + update.bat 接力替换 onefile exe（失败自动回滚）
├── rollback.py        启动自检、成功标记、回滚收尾
├── updater.py         编排状态机 + 事件回调
└── update_source.json 随 exe 打包的默认源（发布方可预置）
publish_update.py      一键发布：算 sha256 → 生成 version.json → 同步 LAN（+Gitee 指引）
version.json.template  清单模板
```

## 二、更新源配置（改源无需重新打包）

优先级：内置默认 < 打包内置 `update_source.json` < 用户覆盖 `~/.printer_scan_update.json`。

用户覆盖文件示例（放到每台机器的用户主目录，可只改源或只改开关）：

```json
{
  "auto_check": true,
  "auto_install": false,
  "manifest_sources": [
    "\\\\192.168.4.82\\share\\共享\\updates\\version.json",
    "https://gitee.com/knightlsy/printer-scan-tool/raw/config/version.json"
  ]
}
```

- `manifest_sources`：候选清单源，**LAN 在前、Gitee 在后**；探测到第一个可用即停止。
- Gitee 兜底源当前指向公开仓库 `knightlsy/printer-scan-tool` 的 `config` 分支 `version.json`
  （公开仓库，客户端匿名可读）。
- `auto_check`：启动后台静默检查（发现新版才弹窗，无更新不打扰）。
- `auto_install`：`false`=发现后由用户点「立即更新」；`true`=下完直接安装重启。

## 三、发布新版本（每次发版执行）

1. 打包出新 exe（沿用 `build_exe_web.bat` 或 PyInstaller 命令）。
2. 一键发布：

```bash
python publish_update.py \
  --exe "dist/打印机扫描工具_v4.exe" \
  --version 4.2.0 \
  --notes "新增在线更新；修复若干问题"
```

（Gitee 仓库已内置默认 `knightlsy/printer-scan-tool`，如需换仓库再传 `--gitee-repo`。）

脚本会：算 SHA256 → 生成 `version.json` → 复制 exe 到 LAN `updates/4.2.0/`
并把 `version.json` 写到 `updates/` 根，同时打印 Gitee 那侧需要同步的内容：

- **version.json**：推到 Gitee 仓库 `config` 分支（覆盖同名文件即可，无需手工改内容）。
- **exe 附件**：到 Gitee 仓库 `latest` release 上传同一个 exe（中文名仍可正常下载，
  客户端会对中文路径做百分号编码）。

> **务必保证 LAN 与 Gitee 上的 version.json 是同一份**（相同 version + sha256），
> 否则会出现「内网说有更新、外网说没有」的分裂。用本脚本发布可避免。

> 自动上传 Gitee 需要私人令牌（带 `projects` 权限），出于安全默认不写进脚本；
> 想全自动可在 CI 里注入令牌后调 Gitee API（参考 `_gitee_publish.py`）。

## 四、客户端行为

- 启动 → 写「成功标记」（让上次更新的 bat 判定成功、清 .bak）→ 报告上次更新结果
  → 按 `auto_check` 后台静默检查。
- 「关于程序」弹窗内有「检查更新」按钮与「启动时自动检查」开关。
- 发现新版 → 弹窗显示 当前版本 → 最新版本 + 更新说明，点「立即更新」：
  下载（带续传、进度、速度）→ SHA256 校验 → 备份当前 exe 为 `.bak`
  → 写 `update.bat` → 主程序退出 → bat 替换并重启 → 新版启动写成功标记。
- **回滚**：SHA256 不通过绝不安装（第一道保险）；新版启动超时未写成功标记，
  bat 自动还原 `.bak` 重启旧版（第二道保险）。

## 五、边界处理

- **网络异常**：清单探测与下载均带超时 + 指数退避重试；全失败静默跳过，绝不阻塞启动。
- **续传**：HTTP 用 `Range`；SMB 用偏移分块复制；`.part` 落盘，中断可续。
- **并发**：下载到独立 `.part`，校验通过才原子 rename 为最终文件。
- **跨平台**：比对/下载/校验为纯 Python；仅「安装替换」按 OS 分派（当前 Windows 完整实现，
  macOS/Linux 已预留 `_write_and_run_helper_posix`）。

## 六、本地自测（无需真实服务器）

```bash
# 在 updates 目录起一个临时 HTTP 服务，模拟 Gitee/公网源
python -m http.server 8000
# 把 update_source.json 的源临时改成 http://127.0.0.1:8000/version.json 即可验证全链路
```
