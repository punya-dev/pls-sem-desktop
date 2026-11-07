use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

pub fn start_backend_if_needed(app: &AppHandle) {
    if is_backend_alive() {
        log::info!("Backend server is already running on port 8721.");
        return;
    }

    let mut candidate_paths = Vec::new();

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            candidate_paths.push(parent.join("statsem-backend.exe"));
            candidate_paths.push(parent.join("statsem-backend"));
            candidate_paths.push(parent.join("binaries").join("statsem-backend.exe"));
            candidate_paths.push(parent.join("binaries").join("statsem-backend"));
            candidate_paths.push(parent.join("resources").join("statsem-backend.exe"));
            candidate_paths.push(parent.join("resources").join("statsem-backend"));
        }
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidate_paths.push(resource_dir.join("statsem-backend.exe"));
        candidate_paths.push(resource_dir.join("statsem-backend"));
        candidate_paths.push(resource_dir.join("binaries").join("statsem-backend.exe"));
        candidate_paths.push(resource_dir.join("binaries").join("statsem-backend"));
    }

    let mut found_path = None;
    for path in candidate_paths {
        if path.exists() && path.is_file() {
            if let Ok(meta) = path.metadata() {
                // Must be a real compiled binary (> 1 KB), not an empty placeholder stub
                if meta.len() > 1024 {
                    found_path = Some(path);
                    break;
                }
            }
        }
    }

    if let Some(exe_path) = found_path {
        log::info!("Launching backend executable: {:?}", exe_path);
        let mut cmd = Command::new(&exe_path);
        cmd.arg("--host").arg("127.0.0.1").arg("--port").arg("8721");

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }

        match cmd.spawn() {
            Ok(child) => {
                log::info!("Spawned backend process PID: {}", child.id());
                let mut lock = BACKEND_CHILD.lock().unwrap();
                *lock = Some(child);
            }
            Err(e) => {
                log::error!("Failed to launch backend sidecar {:?}: {}", exe_path, e);
            }
        }
    } else {
        log::warn!("No packaged statsem-backend executable found. In dev mode, run backend server manually.");
    }
}

pub fn stop_backend() {
    let mut lock = BACKEND_CHILD.lock().unwrap();
    if let Some(mut child) = lock.take() {
        log::info!("Stopping backend process...");
        let _ = child.kill();
    }
}

fn is_backend_alive() -> bool {
    use std::net::TcpStream;
    use std::time::Duration;
    TcpStream::connect_timeout(&"127.0.0.1:8721".parse().unwrap(), Duration::from_millis(200)).is_ok()
}

