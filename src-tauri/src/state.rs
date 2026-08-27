//! 应用全局状态（进程内共享，跨 IPC 命令传递）。
use rusqlite::Connection;
use std::sync::Mutex;

use crate::db;

/// 服务器配置档。
#[derive(Clone, serde::Serialize, serde::Deserialize)]
pub struct ServerProfile {
    pub id: String,
    pub name: String,
    pub host: String,
    pub share: String,
    pub subfolder: String,
    pub username: String,
    pub password: String,
}

impl ServerProfile {
    pub fn unc_base(&self) -> String {
        format!(r"\\{}\{}", self.host, self.share)
    }
    pub fn root_path(&self) -> String {
        format!(r"\\{}\{}\{}", self.host, self.share, self.subfolder)
    }
}

/// 连接配置（由当前生效的 ServerProfile 派生）。
pub struct ConnectionConfig {
    pub host: String,
    pub share: String,
    pub subfolder: String,
    pub username: String,
    pub password: String,
}

impl ConnectionConfig {
    pub fn unc_base(&self) -> String {
        format!(r"\\{}\{}", self.host, self.share)
    }
    pub fn root_path(&self) -> String {
        format!(r"\\{}\{}\{}", self.host, self.share, self.subfolder)
    }
}

/// 应用运行状态。
pub struct AppState {
    pub db: Mutex<Connection>,
    pub connected: Mutex<bool>,
    pub operator: Mutex<String>,
    pub current_id: Mutex<String>,
    /// 当前任务取消令牌（key = task_id）。
    pub cancels:
        Mutex<std::collections::HashMap<String, std::sync::Arc<std::sync::atomic::AtomicBool>>>,
}

impl AppState {
    pub fn new() -> Self {
        let conn = db::open().unwrap_or_else(|_| db::open_in_memory());
        let (operator, current_id) = db::load_meta(&conn);
        AppState {
            db: Mutex::new(conn),
            connected: Mutex::new(false),
            operator: Mutex::new(operator),
            current_id: Mutex::new(current_id),
            cancels: Mutex::new(std::collections::HashMap::new()),
        }
    }

    /// 读取当前生效的服务器档。
    pub fn active_profile(&self) -> ServerProfile {
        let conn = self.db.lock().unwrap();
        let cur = self.current_id.lock().unwrap().clone();
        db::get_profile(&conn, &cur).unwrap_or_else(|| db::default_profile())
    }
}
