//! 审计日志上报（Cloudflare Worker，与 Python 版一致）。
//!
//! 数据表：无（仅 HTTP 上报 + 本地文件兜底）。

use std::sync::Arc;

#[derive(serde::Serialize, Clone)]
pub struct AuditOp {
    pub time: String,
    pub op_type: String,
    pub description: String,
    pub target: String,
    pub success: bool,
    pub reason: String,
}

#[derive(serde::Serialize, Clone)]
pub struct AuditRecord {
    pub start: String,
    pub end: String,
    pub operator: String,
    pub account: String,
    pub server: String,
    pub subfolder: String,
    pub app_version: String,
    pub ops: Vec<AuditOp>,
}

/// 上报到 Worker（尽力而为，绝不影响主流程）。
pub fn upload_record(record: &AuditRecord) {
    if record.ops.is_empty() {
        return;
    }
    let url = "https://printer-scan.knightlsy.cn/api/log";
    let key = "sg_ingest_e590f98784e06a3d";
    let body = match serde_json::to_string(record) {
        Ok(b) => b,
        Err(_) => return,
    };
    // 后台线程执行，避免阻塞主线程
    std::thread::spawn(move || {
        let client = reqwest::blocking::Client::new();
        let _ = client
            .post(url)
            .header("Content-Type", "application/json; charset=utf-8")
            .header("X-Log-Key", key)
            .header("User-Agent", "SCAN.GATE-Rust")
            .body(body)
            .timeout(std::time::Duration::from_secs(10))
            .send();
    });
}

/// 本地兜底落盘（共享不可写时用）。
pub fn write_local_backup(record: &AuditRecord, base_dir: &str) -> Option<String> {
    let dir = base_dir;
    std::fs::create_dir_all(dir).ok()?;
    let start_ts = record.start.replace([':', ' ', '-'], "_").replace('.', "_");
    let fname = format!("log_{}.json", start_ts);
    let path = std::path::Path::new(dir).join(fname);
    let content = serde_json::to_string_pretty(record).ok()?;
    std::fs::write(&path, content).ok()?;
    Some(path.to_string_lossy().to_string())
}

/// 便捷：Arc<AtomicBool> 取消检测辅助（保持签名一致）。
pub fn cancelled(flag: &Arc<std::sync::atomic::AtomicBool>) -> bool {
    flag.load(std::sync::atomic::Ordering::Relaxed)
}
