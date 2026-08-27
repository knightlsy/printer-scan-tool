//! SQLite 配置存储层。
//!
//! 数据表：
//! - `servers`: 服务器配置档（多档管理）
//! - `meta`:   键值元数据（当前档 id、操作人、更新偏好）

use rusqlite::{params, Connection};
use std::path::PathBuf;

use crate::state::ServerProfile;

fn db_path() -> PathBuf {
    // 跟随系统约定：%APPDATA%\SCAN.GATE\scangate.db
    let base = std::env::var("APPDATA")
        .unwrap_or_else(|_| std::env::var("HOME").unwrap_or_else(|_| ".".into()));
    PathBuf::from(base).join("SCAN.GATE")
}

/// 打开数据库（创建目录和表结构）。
pub fn open() -> rusqlite::Result<Connection> {
    let dir = db_path();
    std::fs::create_dir_all(&dir).ok();
    let conn = Connection::open(dir.join("scangate.db"))?;
    init_schema(&conn)?;
    Ok(conn)
}

pub fn open_in_memory() -> Connection {
    let conn = Connection::open_in_memory().expect("内存库打开失败");
    init_schema(&conn).expect("内存库初始化失败");
    conn
}

fn init_schema(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS servers (
            id        TEXT PRIMARY KEY,
            name      TEXT NOT NULL DEFAULT '默认服务器',
            host      TEXT NOT NULL DEFAULT '192.168.4.82',
            share     TEXT NOT NULL DEFAULT 'share',
            subfolder TEXT NOT NULL DEFAULT '共享',
            username  TEXT NOT NULL DEFAULT 'share',
            password  TEXT NOT NULL DEFAULT 'share'
        );
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        "#,
    )
}

pub fn default_profile() -> ServerProfile {
    ServerProfile {
        id: "default".into(),
        name: "默认服务器".into(),
        host: "192.168.4.82".into(),
        share: "share".into(),
        subfolder: "共享".into(),
        username: "share".into(),
        password: "share".into(),
    }
}

pub fn get_profile(conn: &Connection, id: &str) -> Option<ServerProfile> {
    conn.query_row(
        "SELECT id, name, host, share, subfolder, username, password FROM servers WHERE id = ?1",
        params![id],
        |r| {
            Ok(ServerProfile {
                id: r.get(0)?,
                name: r.get(1)?,
                host: r.get(2)?,
                share: r.get(3)?,
                subfolder: r.get(4)?,
                username: r.get(5)?,
                password: r.get(6)?,
            })
        },
    )
    .ok()
}

pub fn list_profiles(conn: &Connection) -> Vec<ServerProfile> {
    let mut stmt = conn
        .prepare("SELECT id, name, host, share, subfolder, username, password FROM servers ORDER BY rowid")
        .ok();
    let mut out = Vec::new();
    if let Some(mut s) = stmt {
        let rows = s
            .query_map([], |r| {
                Ok(ServerProfile {
                    id: r.get(0)?,
                    name: r.get(1)?,
                    host: r.get(2)?,
                    share: r.get(3)?,
                    subfolder: r.get(4)?,
                    username: r.get(5)?,
                    password: r.get(6)?,
                })
            })
            .ok();
        if let Some(rows) = rows {
            for row in rows.flatten() {
                out.push(row);
            }
        }
    }
    out
}

pub fn upsert_profile(conn: &Connection, p: &ServerProfile) -> rusqlite::Result<()> {
    conn.execute(
        "INSERT INTO servers (id, name, host, share, subfolder, username, password)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(id) DO UPDATE SET
           name=excluded.name, host=excluded.host, share=excluded.share,
           subfolder=excluded.subfolder, username=excluded.username, password=excluded.password",
        params![
            p.id,
            p.name,
            p.host,
            p.share,
            p.subfolder,
            p.username,
            p.password
        ],
    )?;
    Ok(())
}

pub fn delete_profile(conn: &Connection, id: &str) -> rusqlite::Result<()> {
    conn.execute("DELETE FROM servers WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn load_meta(conn: &Connection) -> (String, String) {
    let get = |k: &str| -> String {
        conn.query_row("SELECT value FROM meta WHERE key = ?1", params![k], |r| {
            r.get::<_, String>(0)
        })
        .unwrap_or_default()
    };
    let operator = get("operator");
    let current_id = get("current_id");
    (operator, current_id)
}

pub fn save_meta(conn: &Connection, key: &str, value: &str) -> rusqlite::Result<()> {
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![key, value],
    )?;
    Ok(())
}
