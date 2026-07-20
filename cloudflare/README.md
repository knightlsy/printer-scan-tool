# SCAN.GATE 下载反代（Cloudflare Worker）

把 GitHub Releases 上的 exe 通过 Cloudflare 边缘网络分发给用户，国内通常比
ghproxy / GitHub raw 更快更稳。支持断点续传，并对完整下载做边缘缓存。

## 客户端下载地址形式

```
https://<worker>.<sub>.workers.dev/v4.6.0/printer-scan-tool.exe
   ↓ 反代到
https://github.com/knightlsy/printer-scan-tool/releases/download/v4.6.0/printer-scan-tool.exe
```

仅白名单本仓库的 `/vX.Y.Z/*.exe`，拒绝其它请求（非开放代理）。

## 部署方式（二选一）

### 方式 A：Cloudflare 控制台粘贴（无需本机环境、无需给我密钥）
1. 打开 https://dash.cloudflare.com → 左侧 **Workers & Pages** → **Create**。
2. 取个名字（如 `printer-scan-cf-proxy`），点 **Deploy** 进入编辑页。
3. 把本目录 `worker.js` 的内容**全部粘贴**覆盖默认代码 → **Save and Deploy**。
4. 部署完成后得到地址 `https://printer-scan-cf-proxy.<sub>.workers.dev`。
5. 把这个地址发给 AI，AI 会写进 `version.json` 作为升级主链并推送到 GitHub。

### 方式 B：本机 wrangler（适合要绑定自定义域 / 自动化）
```bash
npm install -g wrangler
wrangler login            # 浏览器授权
cd cloudflare
wrangler deploy           # 部署 worker.js（按 wrangler.toml）
# 如需自定义域，取消 wrangler.toml 里 routes 注释并改成你的域名后重部署
```
部署后终端会打印 `*.workers.dev` 地址（或你的自定义域）。

## 自定义域名（国内最稳，可选）
在 Cloudflare 控制台给 Worker 添加自定义域（需你的域名已接入 Cloudflare，
如 `dl.yourdomain.com`）。用户经你的域名访问，经过 Cloudflare 优质线路，速度最佳。

## 上线后如何接入升级
把得到的 Worker 地址发给 AI，AI 会：
1. 在 `version.json` 的 `files[].urls` 最前面插入
   `<worker地址>/v<版本>/printer-scan-tool.exe` 作为主链；
2. 保留 ghproxy / 官方直链作兜底；
3. 经 GitHub API 推送到 master。

之后 `publish_update.py` 加 `--cf-url <worker地址>` 即可让每次发布自动把它置顶。
