use std::env;
use std::fs;
use std::path::Path;

fn main() {
    let target = env::var("TARGET").unwrap_or_default();
    let binaries_dir = Path::new("binaries");
    let _ = fs::create_dir_all(binaries_dir);

    let ext = if target.contains("windows") { ".exe" } else { "" };
    let sidecar_name = format!("statsem-backend-{}{}", target, ext);
    let sidecar_path = binaries_dir.join(&sidecar_name);

    if !sidecar_path.exists() {
        // Create placeholder so tauri_build does not fail in dev when the sidecar hasn't been frozen yet
        let _ = fs::write(&sidecar_path, b"");
    }

    tauri_build::build()
}
