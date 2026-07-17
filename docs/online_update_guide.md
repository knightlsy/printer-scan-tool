# 在线更新系统 · 使用说明

模式：**Gitee 单源**。客户端从 Gitee 公开仓库拉取版本清单与下载包。

## 一、组成

```
scangate/updater/
├── settings.py        更新源与偏好（内置默认 + update_source.json + 用户覆盖文件）
├── manifest.py        版本比对 + 清单探测 fetch_manifest
├── download.py        Downloader：HTTP Range 续传 + SHA256 校验
├── install.py         备份 .bak + update.bat 接力替换 onefile exe（失败自动回滚）
├── rollback.py        启动自检、成功标记、回滚收尾
├── updater.py         编排状态机 + 事件回调
└── update_source.json 随 exe 打包的默认源（Gitee raw URL）
publish_update.py      一键发布：算 sha256 → 生成 version.json → 输出 + Gitee 上传指引
version.json.template  清单模板
```

## 二、更新源配置（改源无需重新打包）

优先级：内置默认 < 打包内置 `update_source.json` < 用户覆盖 `~/.printer_scan_update.json`。

用户覆盖文件示例：

```json
{
  "auto_check": true,
  "auto_install": false,
  "manifest_sources": [
    "https://gitee.com/knightlsy/printer-scan-tool/raw/config/version.json"
  ]
}
```

- `manifest_sources`：清单源列表，当前为 **Gitee `config` 分支的 version.json**（公开仓库，匿名可读）。
- `auto_check`：启动后台静默检查（默认开启）。
- `auto_install`：**默认 `true`（全自动静默更新）**——启动检查到新版本后自动下载、校验、替换并重启应用，无需用户点击确认；仅网络异常/下载失败时安静跳过并在下次启动重试。如需改回「发现后弹窗确认」，把该值改 `false`（或运行时覆盖文件设 `auto_install:false`）。

## 三、发布新版本（每次发版执行）

1. 打包出新 exe（沿用 PyInstaller 命令或 `.spec` 文件）。
2. 一键生成清单：

```bash
python publish_update.py \
  --exe "dist/打印机扫描工具_v4.exe" \
  --version 4.2.0 \
  --notes "更新说明"
```

3. 脚本输出 `_publish_version.json` 并打印 Gitee 同步步骤：
   - **version.json** → 推到 Gitee 仓库的 `config` 分支：
     ```bash
     git checkout config
     cp _publish_version.json version.json
     git add version.json && git commit -m 'release v4.2.0' && git push origin config
     git checkout master
     ```
   - **exe 附件** → 到 Gitee 仓库的 `latest` release 上传新 exe（中文名正常，客户端会自动编码）。

> 客户端下载直链格式：`https://gitee.com/knightlsy/printer-scan-tool/releases/download/latest/<exe名>`

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

- **网络异常**：清单探测与下载均带超时（15s）+ 指数退避重试（3次）；全失败静默跳过，绝不阻塞启动。
- **续传**：HTTP 用 `Range` 头；`.part` 落盘，中断可续。
- **并发**：下载到独立 `.part`，校验通过才原子 rename 为最终文件。
- **中文路径**：URL 自动做百分号编码（`urllib.parse.quote`），中文名 exe 正常下载。

## 六、本地自测

```bash
# 起临时 HTTP 服务模拟 Gitee 源
python -m http.server 8000
# 把 update_source.json 的源临时改成 http://127.0.0.1:8000/version.json 即可验证全链路
```
