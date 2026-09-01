//! IPC 命令层：把前端调用映射到 Rust 后端。
//! 对应原 Python web/api.py 的 28 个接口。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, State, Window};

use crate::state::AppState;

// ---------------- 工具 ---------------- /// 生成取消令牌并登记。
fn register_cancel(state: &AppState, task_id: &str) -> Arc<AtomicBool> {
    let flag = Arc::new(AtomicBool::new(false));
    state
        .cancels
        .lock()
        .unwrap()
        .insert(task_id.to_string(), flag.clone());
    flag
}

fn drop_cancel(state: &AppState, task_id: &str) {
    state.cancels.lock().unwrap().remove(task_id);
}

fn emit(app: &AppHandle, event: &str, payload: impl serde::Serialize + Clone) {
    let _ = app.emit(event, payload);
}

#[derive(serde::Deserialize)]
pub struct ServerFormData {
    pub id: Option<String>,
    pub name: String,
    pub host: String,
    pub share: String,
    pub subfolder: String,
    pub username: String,
    pub password: String,
}

// ---------------- 连接 / 会话 ----------------

#[tauri::command]
pub fn connect(app: AppHandle, state: State<Mutex<AppState>>) -> Result<(), String> {
    emit(
        &app,
        "onStatus",
        &serde_json::json!({"text": "连接中…", "kind": "warn"}),
    );
    let st = state.lock().unwrap();
    let cfg = crate::smb::to_config(&st.active_profile());
    let flag = register_cancel(&st, "connect");
    drop(st);
    let result = crate::smb::connect(&cfg, &flag);
    drop_cancel(&state.lock().unwrap(), "connect");
    if result.is_ok() {
        *state.lock().unwrap().connected.lock().unwrap() = true;
        emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "已连接", "kind": "success"}),
        );
        emit(
            &app,
            "onConfigStatus",
            &serde_json::json!({"text": "已连接", "connected": true}),
        );
        // 立即刷新文件列表
        let st2 = state.lock().unwrap();
        let cfg2 = crate::smb::to_config(&st2.active_profile());
        drop(st2);
        let flag2 = register_cancel(&state.lock().unwrap(), "list");
        let items = crate::smb::list_files(&cfg2, &flag2);
        drop_cancel(&state.lock().unwrap(), "list");
        if let Ok(items) = items {
            emit(&app, "onList", &items);
            emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": format!("共 {} 项", items.len()), "kind": "success"}),
            );
        }
    }
    let _ = app;
    result
}

#[tauri::command]
pub fn disconnect(app: AppHandle, state: State<Mutex<AppState>>) -> Result<(), String> {
    let st = state.lock().unwrap();
    let cfg = crate::smb::to_config(&st.active_profile());
    let flag = register_cancel(&st, "disconnect");
    drop(st);
    let result = crate::smb::disconnect(&cfg, &flag);
    drop_cancel(&state.lock().unwrap(), "disconnect");
    *state.lock().unwrap().connected.lock().unwrap() = false;
    let _ = emit(
        &app,
        "onStatus",
        &serde_json::json!({"text": "已断开", "kind": "warn"}),
    );
    let _ = emit(
        &app,
        "onConfigStatus",
        &serde_json::json!({"text": "未连接", "connected": false}),
    );
    let _ = emit(&app, "onList", &Vec::<crate::smb::FileEntry>::new());
    let _ = app;
    result
}

// ---------------- 服务器配置 ----------------

#[derive(serde::Serialize)]
pub struct ServerView {
    pub id: String,
    pub name: String,
    pub host: String,
    pub subfolder: String,
}

#[tauri::command]
pub fn list_servers(state: State<Mutex<AppState>>) -> Vec<ServerView> {
    let st = state.lock().unwrap();
    let conn = st.db.lock().unwrap();
    crate::db::list_profiles(&conn)
        .into_iter()
        .map(|p| ServerView {
            id: p.id,
            name: p.name,
            host: p.host,
            subfolder: p.subfolder,
        })
        .collect()
}

#[tauri::command]
pub fn save_server(state: State<Mutex<AppState>>, data: ServerFormData) -> Result<String, String> {
    let st = state.lock().unwrap();
    let conn = st.db.lock().unwrap();
    let sid = data.id.unwrap_or_else(|| {
        use rand_help::*;
        new_id()
    });
    let p = crate::state::ServerProfile {
        id: sid.clone(),
        name: data.name,
        host: data.host,
        share: data.share,
        subfolder: data.subfolder,
        username: data.username,
        password: data.password,
    };
    crate::db::upsert_profile(&conn, &p).map_err(|e| e.to_string())?;
    Ok(sid)
}

#[tauri::command]
pub fn delete_server(state: State<Mutex<AppState>>, id: String) -> Result<(), String> {
    let st = state.lock().unwrap();
    let conn = st.db.lock().unwrap();
    crate::db::delete_profile(&conn, &id).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn use_server(app: AppHandle, state: State<Mutex<AppState>>, id: String) -> Result<(), String> {
    let st = state.lock().unwrap();
    let conn = st.db.lock().unwrap();
    if crate::db::get_profile(&conn, &id).is_none() {
        return Err("服务器不存在".into());
    }
    *st.current_id.lock().unwrap() = id.clone();
    crate::db::save_meta(&conn, "current_id", &id).map_err(|e| e.to_string())?;
    emit(&app, "useServer", &serde_json::json!({"id": id}));
    Ok(())
}

#[tauri::command]
pub fn save_config(state: State<Mutex<AppState>>, cfg: serde_json::Value) -> Result<bool, String> {
    // 前端保存连接配置到当前档
    let st = state.lock().unwrap();
    let conn = st.db.lock().unwrap();
    let mut p = st.active_profile();
    if let Some(v) = cfg.get("host").and_then(|v| v.as_str()) {
        p.host = v.into();
    }
    if let Some(v) = cfg.get("share").and_then(|v| v.as_str()) {
        p.share = v.into();
    }
    if let Some(v) = cfg.get("subfolder").and_then(|v| v.as_str()) {
        p.subfolder = v.into();
    }
    if let Some(v) = cfg.get("username").and_then(|v| v.as_str()) {
        p.username = v.into();
    }
    if let Some(v) = cfg.get("password").and_then(|v| v.as_str()) {
        p.password = v.into();
    }
    crate::db::upsert_profile(&conn, &p).map_err(|e| e.to_string())?;
    Ok(true)
}

#[tauri::command]
pub fn set_operator(state: State<Mutex<AppState>>, name: String) -> serde_json::Value {
    if name.trim().is_empty() {
        return serde_json::json!({"ok": false, "error": "姓名不能为空"});
    }
    match (|| {
        let st = state.lock().unwrap();
        *st.operator.lock().unwrap() = name.clone();
        let conn = st.db.lock().unwrap();
        crate::db::save_meta(&conn, "operator", &name)
    })() {
        Ok(()) => serde_json::json!({"ok": true}),
        Err(e) => serde_json::json!({"ok": false, "error": e.to_string()}),
    }
}

#[derive(serde::Serialize)]
pub struct InitData {
    pub app_name: String,
    pub version: String,
    pub connected: bool,
    pub operator: String,
    pub needs_name: bool,
    pub config: ConfigView,
    pub current_id: String,
    pub update: UpdateView,
}

#[derive(serde::Serialize, Default)]
pub struct ConfigView {
    pub host: String,
    pub share: String,
    pub subfolder: String,
    pub username: String,
    pub password: String,
}

#[derive(serde::Serialize, Default)]
pub struct UpdateView {
    pub auto_check: bool,
    pub auto_install: bool,
}

#[tauri::command]
pub fn get_init(state: State<Mutex<AppState>>) -> InitData {
    let st = state.lock().unwrap();
    let op = st.operator.lock().unwrap().clone();
    let connected = *st.connected.lock().unwrap();
    let profile = st.active_profile();
    let cur_id = st.current_id.lock().unwrap().clone();
    drop(st);
    InitData {
        app_name: "SCAN.GATE".into(),
        version: env!("CARGO_PKG_VERSION").into(),
        connected,
        operator: op.clone(),
        needs_name: op.is_empty(),
        config: ConfigView {
            host: profile.host,
            share: profile.share,
            subfolder: profile.subfolder,
            username: profile.username,
            password: profile.password,
        },
        current_id: cur_id,
        update: UpdateView {
            auto_check: true,
            auto_install: false,
        },
    }
}

// ---------------- 文件 ----------------

#[tauri::command]
pub fn refresh(app: AppHandle, state: State<Mutex<AppState>>) {
    if !*state.lock().unwrap().connected.lock().unwrap() {
        emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "请先连接共享", "kind": "error"}),
        );
        return;
    }
    let st = state.lock().unwrap();
    let cfg = crate::smb::to_config(&st.active_profile());
    let flag = register_cancel(&st, "list");
    drop(st);
    let items = crate::smb::list_files(&cfg, &flag);
    drop_cancel(&state.lock().unwrap(), "list");
    match items {
        Ok(items) => {
            let _ = emit(&app, "onList", &items);
            let _ = emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": format!("共 {} 项", items.len()), "kind": "success"}),
            );
        }
        Err(e) => {
            let _ = emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": format!("刷新失败：{}", e), "kind": "error"}),
            );
        }
    }
    let _ = app;
}

#[tauri::command]
pub fn upload(app: AppHandle, state: State<Mutex<AppState>>) {
    use tauri_plugin_dialog::DialogExt;
    let picked = app.dialog().file().blocking_pick_files();
    let paths = match picked {
        Some(v) => v
            .into_iter()
            .map(|fp| match fp.into_path() {
                Ok(pb) => pb.to_string_lossy().to_string(),
                Err(_) => String::new(),
            })
            .collect::<Vec<_>>(),
        None => {
            let _ = emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": "未选择文件", "kind": "warn"}),
            );
            return;
        }
    };

    let st = state.lock().unwrap();
    let cfg = crate::smb::to_config(&st.active_profile());
    let dest = cfg.root_path();
    let flag = register_cancel(&st, "upload");
    drop(st);

    let mut ok = 0usize;
    let mut fail = 0usize;
    for p in &paths {
        if flag.load(Ordering::Relaxed) {
            break;
        }
        let name = std::path::Path::new(p)
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let dst = format!(r"{}\{}", dest, name);
        if crate::smb::copy_file(p, &dst, &flag, |_p, _m| {}).is_ok() {
            ok += 1;
        } else {
            fail += 1;
        }
    }
    drop_cancel(&state.lock().unwrap(), "upload");

    let msg = format!("上传完成：成功 {} / 失败 {}", ok, fail);
    let _ = emit(
        &app,
        "onStatus",
        &serde_json::json!({"text": msg, "kind": if fail == 0 { "success" } else { "warn" }}),
    );
    // 刷新列表
    let items = {
        let st2 = state.lock().unwrap();
        let cfg2 = crate::smb::to_config(&st2.active_profile());
        let flag2 = register_cancel(&st2, "list");
        drop(st2);
        crate::smb::list_files(&cfg2, &flag2)
    };
    drop_cancel(&state.lock().unwrap(), "list");
    if let Ok(items) = items {
        let _ = emit(&app, "onList", &items);
    }
}

#[tauri::command]
pub fn download(app: AppHandle, state: State<Mutex<AppState>>, path: String) {
    if path.is_empty() {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "请先选择要下载的文件", "kind": "error"}),
        );
        return;
    }
    if !*state.lock().unwrap().connected.lock().unwrap() {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "请先连接共享", "kind": "error"}),
        );
        return;
    }

    let name = std::path::Path::new(&path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or("download".into());

    use tauri_plugin_dialog::DialogExt;
    let picked = app.dialog().file().blocking_save_file();
    let dest = match picked {
        Some(p) => match p.into_path() {
            Ok(pb) => pb.to_string_lossy().to_string(),
            Err(_) => return,
        },
        None => return,
    };

    let st = state.lock().unwrap();
    let flag = register_cancel(&st, "download");
    drop(st);
    let r = crate::smb::copy_file(&path, &dest, &flag, |_p, _m| {});
    drop_cancel(&state.lock().unwrap(), "download");
    if r.is_ok() {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "下载完成", "kind": "success"}),
        );
    } else {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": format!("下载失败：{}", r.unwrap_err()), "kind": "error"}),
        );
    }
}

#[tauri::command]
pub fn delete(app: AppHandle, state: State<Mutex<AppState>>, path: String) {
    if !*state.lock().unwrap().connected.lock().unwrap() {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "请先连接共享", "kind": "error"}),
        );
        return;
    }
    let r = crate::smb::delete_path(&path);
    if r.is_ok() {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "删除完成", "kind": "success"}),
        );
        let items = {
            let st = state.lock().unwrap();
            let cfg = crate::smb::to_config(&st.active_profile());
            let flag = register_cancel(&st, "list");
            drop(st);
            crate::smb::list_files(&cfg, &flag)
        };
        drop_cancel(&state.lock().unwrap(), "list");
        if let Ok(items) = items {
            let _ = emit(&app, "onList", &items);
        }
    } else {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": format!("删除失败：{}", r.unwrap_err()), "kind": "error"}),
        );
    }
}

// ---------------- 预览 / PDF ----------------

#[derive(serde::Serialize)]
pub struct PreviewResult {
    pub image: Option<String>, // base64 data URL
    pub page: u32,
    pub total: u32,
    pub pdf: bool,
}

#[tauri::command]
pub fn preview(app: AppHandle, state: State<Mutex<AppState>>, path: String, page: u32) {
    if path.is_empty() {
        let _ = emit(&app, "onPreview", &serde_json::json!({}));
        return;
    }
    let st = state.lock().unwrap();
    let flag = register_cancel(&st, "preview");
    drop(st);
    let name = std::path::Path::new(&path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or(path.clone());
    let r = crate::pdf::make_preview(&path, page, &flag);
    drop_cancel(&state.lock().unwrap(), "preview");
    match r {
        Ok(pr) => {
            let _ = emit(
                &app,
                "onPreview",
                &serde_json::json!({
                    "data": pr.image,
                    "name": name,
                    "page": pr.page,
                    "total": pr.total,
                    "pdf": pr.pdf,
                    "error": null,
                }),
            );
        }
        Err(e) => {
            let msg = if e.contains("PyMuPDF") || e.contains("打开 PDF") {
                e
            } else {
                "无法预览此文件".to_string()
            };
            let _ = emit(
                &app,
                "onPreview",
                &serde_json::json!({"error": msg, "data": null}),
            );
        }
    }
}

#[tauri::command]
pub fn pick_pdf(app: AppHandle) {
    use tauri_plugin_dialog::DialogExt;
    let picked = app
        .dialog()
        .file()
        .add_filter("PDF 文件", &["pdf"])
        .blocking_pick_file();
    if let Some(first) = picked {
        let first = match first.into_path() {
            Ok(pb) => pb.to_string_lossy().to_string(),
            Err(_) => return,
        };
        let _ = emit(&app, "onPickPdf", &serde_json::json!({"path": first}));
    } else {
        let _ = emit(
            &app,
            "onStatus",
            &serde_json::json!({"text": "未选择 PDF 文件", "kind": "warn"}),
        );
    }
}

#[tauri::command]
pub fn compress_pdf(
    app: AppHandle,
    state: State<Mutex<AppState>>,
    path: String,
    level: String,
    rate: Option<u32>,
) {
    let st = state.lock().unwrap();
    let flag = register_cancel(&st, "compress");
    drop(st);
    let r = crate::pdf::compress(&path, &level, rate, &flag);
    drop_cancel(&state.lock().unwrap(), "compress");
    match r {
        Ok(dst) => {
            let _ = emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": format!("压缩完成，已保存：{}", dst), "kind": "success"}),
            );
        }
        Err(e) => {
            let _ = emit(
                &app,
                "onStatus",
                &serde_json::json!({"text": format!("压缩失败：{}", e), "kind": "error"}),
            );
        }
    }
}

// ---------------- 窗口控制 ----------------

#[tauri::command]
pub fn minimize(window: Window) {
    let _ = window.minimize();
}

#[tauri::command]
pub fn toggle_maximize(window: Window) {
    if window.is_maximized().unwrap_or(false) {
        let _ = window.unmaximize();
    } else {
        let _ = window.maximize();
    }
}

#[tauri::command]
pub fn close_window(app: AppHandle) {
    let _ = app.exit(0);
}

#[tauri::command]
pub fn open_url(url: String) {
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("cmd")
            .args(["/C", "start", &url])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("xdg-open")
            .arg(&url)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
    }
}

#[tauri::command]
pub fn resize_window(window: Window, width: f64, height: f64, _direction: String) {
    let _ = window.set_size(tauri::PhysicalSize::new(width as u32, height as u32));
}

/// 返回主窗口当前像素尺寸，供前端八向缩放逻辑同步初始状态。
#[tauri::command]
pub fn get_window_rect(window: Window) -> Result<serde_json::Value, String> {
    let size = window.outer_size().map_err(|e| e.to_string())?;
    let inner = window.inner_size().map_err(|e| e.to_string())?;
    Ok(serde_json::json!({
        "width": size.width,
        "height": size.height,
        "innerWidth": inner.width,
        "innerHeight": inner.height,
    }))
}

// ---------------- 取消 / 其它 ----------------

#[tauri::command]
pub fn cancel(state: State<Mutex<AppState>>, task_id: String) {
    let cancels = state.lock().unwrap();
    let map = cancels.cancels.lock().unwrap();
    let found = map.get(&task_id).cloned();
    drop(map);
    drop(cancels);
    if let Some(f) = found {
        f.store(true, Ordering::Relaxed);
    }
}

#[derive(serde::Serialize)]
pub struct AboutData {
    pub app_name: String,
    pub version: String,
    pub author: String,
    pub copyright: String,
}

#[tauri::command]
pub fn about() -> AboutData {
    AboutData {
        app_name: "SCAN.GATE".into(),
        version: env!("CARGO_PKG_VERSION").into(),
        author: "knightlsy".into(),
        copyright: "© 2026 knightlsy. 版权所有".into(),
    }
}

// ---------------- 更新（接 tauri-plugin-updater） ----------------

/// 检查更新：调用 updater 插件拉取 manifest，发现新版时通过 onUpdateFound 事件推送。
/// 前端 checkUpdate() 调用时传 false（非静默），由插件自行处理下载/安装进度事件。
#[tauri::command]
pub async fn check_update(app: AppHandle) -> Result<serde_json::Value, String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => {
            let current = env!("CARGO_PKG_VERSION").to_string();
            let _ = app.emit(
                "onUpdateFound",
                &serde_json::json!({
                    "version": update.version,
                    "notes": update.body,
                    "download_url": update.download_url.to_string(),
                    "current": current,
                }),
            );
            Ok(serde_json::json!({"has_update": true}))
        }
        Ok(None) => {
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "up_to_date", "text": "已是最新版本"}),
            );
            Ok(serde_json::json!({"has_update": false}))
        }
        Err(e) => {
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "error", "text": format!("检查更新失败：{}", e)}),
            );
            Err(e.to_string())
        }
    }
}

/// 下载并安装更新（manifest 含直链时自动完成，否则回退到手动下载页）。
#[tauri::command]
pub async fn download_and_install_update(app: AppHandle) -> Result<(), String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => {
            let app2 = app.clone();
            let mut downloaded: u64 = 0;
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "checking", "text": "开始下载更新…"}),
            );
            update
                .download(
                    move |chunk_len: usize, total: Option<u64>| {
                        downloaded = downloaded.saturating_add(chunk_len as u64);
                        if let Some(total) = total {
                            let pct = (downloaded as f64 / total as f64 * 100.0).min(100.0) as u32;
                            let _ = app2.emit(
                                "onUpdateStatus",
                                &serde_json::json!({
                                    "kind": "downloading",
                                    "text": format!("下载中…{}%", pct),
                                    "percent": pct,
                                }),
                            );
                        } else {
                            let _ = app2.emit(
                                "onUpdateStatus",
                                &serde_json::json!({
                                    "kind": "downloading",
                                    "text": format!("下载中…{}MB", downloaded >> 20),
                                }),
                            );
                        }
                    },
                    || {
                        let _ = app2.emit(
                            "onUpdateStatus",
                            &serde_json::json!({"kind": "downloaded", "text": "下载完成，正在安装…"}),
                        );
                    },
                )
                .await
                .map_err(|e| e.to_string())?;
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "installing", "text": "下载完成，正在安装…"}),
            );
            update.install().map_err(|e| e.to_string())?;
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "updated", "text": "更新完成，应用将重启"}),
            );
            Ok(())
        }
        Ok(None) => {
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "need_manual", "text": "已是最新版本，无需更新"}),
            );
            Ok(())
        }
        Err(e) => {
            let _ = app.emit(
                "onUpdateStatus",
                &serde_json::json!({"kind": "error", "text": format!("更新失败：{}", e)}),
            );
            Err(e.to_string())
        }
    }
}

#[tauri::command]
pub fn set_update_prefs(
    _auto_check: Option<bool>,
    _auto_install: Option<bool>,
) -> serde_json::Value {
    serde_json::json!({})
}
#[tauri::command]
pub fn startup_update_check() {}

/// 生成短 id（避免额外依赖，用时间+计数器）。
mod rand_help {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    pub fn new_id() -> String {
        let t = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_micros() as u64;
        let n = SEQ.fetch_add(1, Ordering::Relaxed);
        format!("{:x}{:x}", t, n)
    }
}
