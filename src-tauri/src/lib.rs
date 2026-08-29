use std::sync::Mutex;
use tauri::Builder;

mod audit;
mod commands;
mod db;
mod pdf;
mod smb;
mod state;

use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = AppState::new();

    Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Mutex::new(state))
        .invoke_handler(tauri::generate_handler![
            // 连接/会话
            commands::connect,
            commands::disconnect,
            commands::list_servers,
            commands::save_server,
            commands::delete_server,
            commands::use_server,
            commands::save_config,
            commands::get_init,
            commands::set_operator,
            // 文件
            commands::refresh,
            commands::upload,
            commands::download,
            commands::delete,
            commands::preview,
            // PDF
            commands::pick_pdf,
            commands::compress_pdf,
            // 更新
            commands::check_update,
            commands::download_and_install_update,
            commands::set_update_prefs,
            commands::startup_update_check,
            // 窗口
            commands::minimize,
            commands::toggle_maximize,
            commands::close_window,
            commands::open_url,
            commands::resize_window,
            // 其他
            commands::cancel,
            commands::about,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
