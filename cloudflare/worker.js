/**
 * SCAN.GATE 下载反代 Worker
 * ----------------------------------------------------------------------------
 * 作用：把 GitHub Releases 上的 exe 通过 Cloudflare 边缘网络分发给用户，
 *       相当于一个跑在 Cloudflare 骨干网上的 ghproxy，国内通常更快更稳。
 *       支持断点续传（透传 Range），并对完整下载做边缘缓存。
 *
 * 安全：仅白名单本仓库的版本化 .exe（路径形如 /vX.Y.Z/printer-scan-tool.exe），
 *       拒绝其它任何请求，杜绝被当成开放代理滥用。
 *
 * 部署后地址形如：https://<worker-name>.<sub>.workers.dev
 * 客户端下载：     https://<worker-name>.<sub>.workers.dev/v4.6.0/printer-scan-tool.exe
 *   -> 实际反代到 https://github.com/knightlsy/printer-scan-tool/releases/download/v4.6.0/printer-scan-tool.exe
 */

const OWNER = "knightlsy";
const REPO = "printer-scan-tool";
const BASE = `https://github.com/${OWNER}/${REPO}/releases/download/`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 去掉前导斜杠：/v4.6.0/printer-scan-tool.exe -> v4.6.0/printer-scan-tool.exe
    const path = url.pathname.replace(/^\/+/, "");
    if (!path) {
      return new Response(
        "SCAN.GATE CF Proxy\n用法: /<tag>/<file>.exe，例如 /v4.6.0/printer-scan-tool.exe",
        { status: 400, headers: { "Content-Type": "text/plain; charset=utf-8" } }
      );
    }

    // 白名单校验：第一段必须是 vX.Y.Z 形式的 tag，且文件名以 .exe 结尾
    const seg = path.split("/");
    const tag = seg[0] || "";
    const file = seg[seg.length - 1] || "";
    const tagOk = /^v\d+\.\d+\.\d+$/.test(tag);
    const fileOk = file.toLowerCase().endsWith(".exe");
    if (!tagOk || !fileOk) {
      return new Response("仅允许下载本仓库的版本化 exe", { status: 403 });
    }

    const target = BASE + path;

    // 透传客户端 Range，支持断点续传
    const headers = { "User-Agent": "SCAN-GATE-CF-Proxy" };
    const range = request.headers.get("Range");
    if (range) headers["Range"] = range;

    let upstream;
    try {
      upstream = await fetch(target, { headers, redirect: "follow" });
    } catch (e) {
      return new Response("上游 GitHub 拉取失败：" + String(e), { status: 502 });
    }

    const respHeaders = new Headers(upstream.headers);
    respHeaders.set("Access-Control-Allow-Origin", "*");
    // 允许边缘缓存完整下载，加速后续同版本请求
    respHeaders.set("Cache-Control", "public, max-age=86400");

    return new Response(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  },
};
