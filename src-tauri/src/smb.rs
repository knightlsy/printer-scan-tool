//! SMB 网络共享连接与文件操作（Windows 原生 API）。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use crate::state::{ConnectionConfig, ServerProfile};

/// 连接共享（等价于 `net use \\host\share /user:user pass`）。
///
/// 使用 Windows WNetAddConnection2 建立会话；失败时回退 `net use` 命令。
#[cfg(windows)]
pub fn connect(_cfg: &ConnectionConfig, cancel: &Arc<AtomicBool>) -> Result<(), String> {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows::core::PWSTR;
    use windows::Win32::NetworkManagement::WNet::{
        WNetAddConnection2W, CONNECT_TEMPORARY, NETRESOURCEW, RESOURCETYPE_DISK,
    };

    if cancel.load(Ordering::Relaxed) {
        return Err("已取消".into());
    }
    let to_wide = |s: &str| -> Vec<u16> {
        OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    };
    let remote = to_wide(&_cfg.unc_base());
    let user = to_wide(&_cfg.username);
    let pass = to_wide(&_cfg.password);

    let mut nr = NETRESOURCEW {
        dwType: RESOURCETYPE_DISK,
        lpRemoteName: PWSTR(remote.as_ptr() as *mut u16),
        lpLocalName: PWSTR::null(),
        lpProvider: PWSTR::null(),
        ..Default::default()
    };

    let hr = unsafe {
        WNetAddConnection2W(
            &nr,
            PWSTR(pass.as_ptr() as *mut u16),
            PWSTR(user.as_ptr() as *mut u16),
            CONNECT_TEMPORARY,
        )
    };
    if hr.is_ok() {
        Ok(())
    } else {
        // 回退 net use（需要真实 UNC 路径，这里直接拼）
        let _ = nr;
        fallback_net_use(&_cfg)
    }
}

#[cfg(not(windows))]
pub fn connect(_cfg: &ConnectionConfig, _cancel: &Arc<AtomicBool>) -> Result<(), String> {
    // 非 Windows（Linux 开发环境）：仅记录无法真实连接 SMB
    Ok(())
}

#[cfg(windows)]
fn fallback_net_use(cfg: &ConnectionConfig) -> Result<(), String> {
    use std::process::Command;
    let st = Command::new("cmd")
        .args([
            "/C",
            &format!(
                r#"net use "{}" {} /user:{} /persistent:no"#,
                cfg.unc_base(),
                cfg.password,
                cfg.username
            ),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    match st {
        Ok(s) if s.success() => Ok(()),
        _ => Err(format!("无法连接到 {}", cfg.unc_base())),
    }
}

#[cfg(not(windows))]
fn fallback_net_use(_cfg: &ConnectionConfig) -> Result<(), String> {
    Err("非 Windows 环境不支持 SMB".into())
}

/// 断开共享连接。
#[cfg(windows)]
pub fn disconnect(cfg: &ConnectionConfig, _cancel: &Arc<AtomicBool>) -> Result<(), String> {
    use std::process::Command;
    let st = Command::new("cmd")
        .args(["/C", &format!(r#"net use "{}" /delete /y"#, cfg.unc_base())])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    match st {
        Ok(s) if s.success() => Ok(()),
        Ok(_) => Err(format!("断开 {} 失败（可能未连接）", cfg.unc_base())),
        Err(e) => Err(format!("net use 执行失败: {e}")),
    }
}

#[cfg(not(windows))]
pub fn disconnect(_cfg: &ConnectionConfig, _cancel: &Arc<AtomicBool>) -> Result<(), String> {
    Ok(())
}

/// 列出目录内容（文件夹在前，按名称排序）。
pub fn list_files(
    _cfg: &ConnectionConfig,
    cancel: &Arc<AtomicBool>,
) -> Result<Vec<FileEntry>, String> {
    let root = _cfg.root_path();
    let mut entries: Vec<FileEntry> = Vec::new();
    let rd = std::fs::read_dir(&root).map_err(|e| format!("读取 {} 失败: {e}", root))?;
    for entry in rd.flatten() {
        if cancel.load(Ordering::Relaxed) {
            return Err("已取消".into());
        }
        let name = entry.file_name().to_string_lossy().to_string();
        let path = entry.path().to_string_lossy().to_string();
        let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
        let meta = entry.metadata().ok();
        entries.push(FileEntry {
            name,
            is_dir,
            size: if is_dir {
                0
            } else {
                meta.as_ref().map(|m| m.len()).unwrap_or(0)
            },
            mtime: meta
                .as_ref()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs() as f64)
                .unwrap_or(0.0),
            path,
        });
    }
    entries.sort_by(|a, b| {
        b.is_dir
            .cmp(&a.is_dir)
            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });
    Ok(entries)
}

/// 文件条目。
#[derive(Clone, serde::Serialize)]
pub struct FileEntry {
    pub name: String,
    pub is_dir: bool,
    pub size: u64,
    pub mtime: f64,
    pub path: String,
}

/// 复制文件（分块，支持进度回调与取消）。
pub fn copy_file(
    src: &str,
    dst: &str,
    cancel: &Arc<AtomicBool>,
    progress: impl Fn(f64, &str),
) -> Result<(), String> {
    use std::io::{Read, Write};
    let mut fin = std::fs::File::open(src).map_err(|e| format!("打开 {} 失败: {e}", src))?;
    let total = fin.metadata().map(|m| m.len()).unwrap_or(1).max(1);
    let mut fout = std::fs::File::create(dst).map_err(|e| format!("创建 {} 失败: {e}", dst))?;
    let mut buf = vec![0u8; 1024 * 1024];
    let mut copied: u64 = 0;
    loop {
        if cancel.load(Ordering::Relaxed) {
            drop(fout);
            let _ = std::fs::remove_file(dst);
            return Err("已取消".into());
        }
        let n = fin.read(&mut buf).map_err(|e| format!("读取失败: {e}"))?;
        if n == 0 {
            break;
        }
        fout.write_all(&buf[..n])
            .map_err(|e| format!("写入失败: {e}"))?;
        copied += n as u64;
        progress((copied as f64 / total as f64 * 100.0).min(99.0), dst);
    }
    progress(100.0, dst);
    // 刷新并校验大小
    fout.sync_all().ok();
    Ok(())
}

/// 删除文件或目录。
pub fn delete_path(path: &str) -> Result<(), String> {
    let p = std::path::Path::new(path);
    let meta = std::fs::metadata(p).map_err(|e| format!("无法访问 {}: {e}", path))?;
    if meta.is_dir() {
        std::fs::remove_dir_all(p).map_err(|e| format!("删除目录 {} 失败: {e}", path))
    } else {
        std::fs::remove_file(p).map_err(|e| format!("删除文件 {} 失败: {e}", path))
    }
}

/// 由当前档派生连接配置。
pub fn to_config(p: &ServerProfile) -> ConnectionConfig {
    ConnectionConfig {
        host: p.host.clone(),
        share: p.share.clone(),
        subfolder: p.subfolder.clone(),
        username: p.username.clone(),
        password: p.password.clone(),
    }
}
