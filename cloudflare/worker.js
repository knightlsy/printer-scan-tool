/**
 * SCAN.GATE 综合 Worker（经典 Service Worker 格式）
 * ----------------------------------------------------------------------------
 * 1) 下载反代：把 GitHub Releases 上的 exe / zip 经 Cloudflare 边缘分发
 *    （白名单 /vX.Y.Z/*.exe 与 /vX.Y.Z/*.zip，透传 Range 断点续传，边缘缓存）。
 * 2) 操作审计日志：客户端在「连接会话」结束时把汇总日志 POST 到 /api/log，
 *    本 Worker 写入 KV（LOG_KV 绑定）。GET /api/logs（需 LOG_VIEW_KEY 口令）
 *    分页查询；GET /logs 提供密码保护的查询页面。
 *
 * 安全：
 * - 反代仅白名单本仓库版本化 exe，拒绝其它路径（非开放代理）。
 * - 日志写入需 X-Log-Key 等于 INGEST_KEY（防公开灌水）。
 * - 日志查询需 key=LOG_VIEW_KEY（或 Authorization: Bearer）口令。
 *
 * 部署后地址：https://printer-scan.knightlsy.cn （自定义域）
 *   下载：/v4.6.1/printer-scan-tool.exe
 *   写日志：POST /api/log   （header: X-Log-Key）
 *   查日志：GET  /api/logs?key=口令&limit=50&cursor=xxx
 *   查询页：GET  /logs
 */

const OWNER = "knightlsy";
const REPO = "printer-scan-tool";
const BASE = "https://github.com/" + OWNER + "/" + REPO + "/releases/download/";

// 查询页 HTML（部署时由脚本注入，见 cloudflare/logpage.html）
const LOG_PAGE = __LOG_PAGE_JSON__;

function json(body, status) {
  status = status || 200;
  return new Response(JSON.stringify(body), {
    status: status,
    headers: { "Content-Type": "application/json; charset=utf-8",
               "Access-Control-Allow-Origin": "*" },
  });
}

function normalizeOp(o) {
  if (!o || typeof o !== "object") return null;
  return {
    time: String(o.time || ""),
    op_type: String(o.op_type || "操作"),
    description: String(o.description || "").slice(0, 500),
    target: String(o.target || "").slice(0, 300),
    success: o.success === false ? false : true,
    reason: String(o.reason || "").slice(0, 300),
  };
}

// ---------------- 日志写入 ----------------
async function handleIngest(request) {
  const key = request.headers.get("X-Log-Key") || "";
  if (!INGEST_KEY || key !== INGEST_KEY) {
    return json({ ok: false, error: "unauthorized" }, 401);
  }
  let body;
  try { body = await request.json(); } catch (e) { return json({ ok: false, error: "bad json" }, 400); }
  if (!body || typeof body !== "object") return json({ ok: false, error: "empty" }, 400);

  const ts = Date.now();
  const rand = Math.random().toString(36).slice(2, 8);
  const rec = {
    id: ts + ":" + rand,
    ts: ts,
    start: String(body.start || "").slice(0, 24),
    end: String(body.end || "").slice(0, 24),
    operator: String(body.operator || body.account || "未知").slice(0, 40),
    account: String(body.account || "").slice(0, 80),
    server: String(body.server || "").slice(0, 140),
    subfolder: String(body.subfolder || "").slice(0, 80),
    app_version: String(body.app_version || "").slice(0, 60),
    op_count: Array.isArray(body.ops) ? body.ops.length : 0,
    ops: (Array.isArray(body.ops) ? body.ops : []).slice(0, 200).map(normalizeOp).filter(Boolean),
    cf_ip: request.headers.get("CF-Connecting-IP") || "",
    cf_country: request.headers.get("CF-IPCountry") || "",
  };
  // key 按时间戳补零前缀，保证 KV list 升序即时间序；同毫秒靠 rand 区分
  const kvKey = "log:" + String(ts).padStart(15, "0") + ":" + rand;
  try {
    await LOG_KV.put(kvKey, JSON.stringify(rec));
    return json({ ok: true, id: kvKey });
  } catch (e) {
    return json({ ok: false, error: "kv write failed: " + String(e) }, 500);
  }
}

// ---------------- 日志查询（需口令） ----------------
async function handleQuery(request) {
  const url = new URL(request.url);
  const qkey = url.searchParams.get("key") ||
               (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "") || "";
  if (!LOG_VIEW_KEY || qkey !== LOG_VIEW_KEY) {
    return json({ ok: false, error: "unauthorized" }, 401);
  }
  let limit = parseInt(url.searchParams.get("limit") || "50", 10);
  if (!Number.isFinite(limit) || limit < 1) limit = 50;
  limit = Math.min(limit, 200);
  const cursor = url.searchParams.get("cursor") || undefined;

  let listed;
  try {
    listed = await LOG_KV.list({ prefix: "log:", limit: limit, cursor: cursor });
  } catch (e) {
    return json({ ok: false, error: "kv list failed: " + String(e) }, 500);
  }

  const entries = [];
  for (const k of listed.keys) {
    try {
      const v = await LOG_KV.get(k.name);
      if (v) entries.push(JSON.parse(v));
    } catch (e) { /* 跳过损坏项 */ }
  }
  entries.sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); }); // 最新在前

  return json({
    ok: true,
    entries: entries,
    cursor: listed.cursor || null,
    list_complete: !!listed.list_complete,
  });
}

// ---------------- 下载反代（白名单） ----------------
async function handleProxy(request) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/+/, "");
  if (!path) {
    return new Response(
      "SCAN.GATE CF Worker\n下载: /<tag>/<file>.exe | /<tag>/<file>.zip  日志页: /logs",
      { status: 400, headers: { "Content-Type": "text/plain; charset=utf-8" } }
    );
  }
  const seg = path.split("/");
  const tag = seg[0] || "";
  const file = seg[seg.length - 1] || "";
  const tagOk = /^v\d+\.\d+\.\d+$/.test(tag);
  const low = file.toLowerCase();
  const fileOk = low.endsWith(".exe") || low.endsWith(".zip");
  if (!tagOk || !fileOk) {
    return new Response("仅允许下载本仓库的版本化 exe / zip", { status: 403 });
  }

  const target = BASE + path;
  const headers = { "User-Agent": "SCAN-GATE-CF-Proxy" };
  const range = request.headers.get("Range");
  if (range) headers["Range"] = range;

  let upstream;
  try {
    upstream = await fetch(target, { headers: headers, redirect: "follow" });
  } catch (e) {
    return new Response("上游 GitHub 拉取失败：" + String(e), { status: 502 });
  }

  const respHeaders = new Headers(upstream.headers);
  respHeaders.set("Access-Control-Allow-Origin", "*");
  respHeaders.set("Cache-Control", "public, max-age=86400");
  return new Response(upstream.body, { status: upstream.status, headers: respHeaders });
}

async function handleMain(request) {
  const url = new URL(request.url);
  const p = url.pathname;
  if (p === "/api/log" && request.method === "POST") return handleIngest(request);
  if (p === "/api/logs" && request.method === "GET") return handleQuery(request);
  if (p === "/logs" || p === "/logs/") {
    return new Response(LOG_PAGE, {
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  return handleProxy(request);
}

addEventListener("fetch", function (event) {
  event.respondWith(handleMain(event.request));
});
