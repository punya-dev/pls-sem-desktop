mod license;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_fs::init())
    .invoke_handler(tauri::generate_handler![
      license::get_license_status,
      license::activate_license,
      license::deactivate_license,
      license::get_machine_fingerprint,
      license::export_license_token,
      license::dev_mint_token,
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

