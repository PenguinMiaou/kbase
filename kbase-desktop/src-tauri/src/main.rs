// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, RunEvent, WindowEvent,
};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};

const HOST: &str = "127.0.0.1";
const PORT: u16 = 8765;

struct PythonProcess(Mutex<Option<Child>>);

// ── Server health checks ───────────────────────────────────────────

async fn is_server_running() -> bool {
    let url = format!("http://{}:{}/api/version", HOST, PORT);
    match reqwest::get(&url).await {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

async fn wait_for_server(timeout_secs: u64) -> bool {
    let url = format!("http://{}:{}/api/version", HOST, PORT);
    let start = std::time::Instant::now();
    while start.elapsed() < Duration::from_secs(timeout_secs) {
        if let Ok(resp) = reqwest::get(&url).await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    false
}

// ── Python discovery (bundled → uv tool → system) ─────────────────

fn app_resource_dir() -> Option<PathBuf> {
    // In bundled .app: Contents/Resources/
    let exe = std::env::current_exe().ok()?;
    let resources = exe.parent()?.parent()?.join("Resources");
    if resources.exists() {
        Some(resources)
    } else {
        None
    }
}

fn find_python() -> Option<String> {
    let home = dirs::home_dir()?;

    // 1. Bundled venv inside .app (offline/fat mode)
    if let Some(res) = app_resource_dir() {
        let bundled = res.join("python-env/bin/python3");
        if bundled.exists() {
            return Some(bundled.to_string_lossy().to_string());
        }
        // Windows
        let bundled_win = res.join("python-env/Scripts/python.exe");
        if bundled_win.exists() {
            return Some(bundled_win.to_string_lossy().to_string());
        }
    }

    // 2. uv tool install location
    let uv_python = home.join(".local/share/uv/tools/kbase-app/bin/python3");
    if uv_python.exists() {
        return Some(uv_python.to_string_lossy().to_string());
    }
    // Windows uv path
    let uv_python_win = home.join(".local/share/uv/tools/kbase-app/Scripts/python.exe");
    if uv_python_win.exists() {
        return Some(uv_python_win.to_string_lossy().to_string());
    }

    // 3. Source install venv
    let venv_python = home.join("kbase/.venv/bin/python3");
    if venv_python.exists() {
        return Some(venv_python.to_string_lossy().to_string());
    }

    // 4. System python with kbase installed
    for cmd in &["python3", "python"] {
        if let Ok(output) = std::process::Command::new(cmd)
            .args(["-c", "import kbase; print('ok')"])
            .output()
        {
            if output.status.success() {
                return Some(cmd.to_string());
            }
        }
    }

    None
}

fn find_uv() -> Option<String> {
    let home = dirs::home_dir()?;

    // Check common uv locations
    for path in &[
        home.join(".local/bin/uv"),
        home.join(".cargo/bin/uv"),
        PathBuf::from("/opt/homebrew/bin/uv"),
        PathBuf::from("/usr/local/bin/uv"),
    ] {
        if path.exists() {
            return Some(path.to_string_lossy().to_string());
        }
    }

    // Try PATH
    if let Ok(output) = std::process::Command::new("uv").arg("--version").output() {
        if output.status.success() {
            return Some("uv".to_string());
        }
    }

    None
}

// ── Online bootstrap (install uv → install kbase) ─────────────────

async fn run_online_setup(app: tauri::AppHandle) -> Result<(), String> {
    // Step 1: Install uv if missing
    if find_uv().is_none() {
        let _ = app.emit("setup-progress", serde_json::json!({
            "step": "uv", "status": "installing", "message": "Installing uv package manager..."
        }));

        #[cfg(not(target_os = "windows"))]
        let result = Command::new("sh")
            .args(["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
            .output()
            .await;

        #[cfg(target_os = "windows")]
        let result = Command::new("powershell")
            .args(["-ExecutionPolicy", "ByPass", "-c", "irm https://astral.sh/uv/install.ps1 | iex"])
            .output()
            .await;

        match result {
            Ok(out) if out.status.success() => {},
            Ok(out) => return Err(format!("uv install failed: {}", String::from_utf8_lossy(&out.stderr))),
            Err(e) => return Err(format!("Failed to run uv installer: {}", e)),
        }
    }

    let uv = find_uv().ok_or("uv not found after install")?;

    // Step 2: Install kbase-app via uv
    let _ = app.emit("setup-progress", serde_json::json!({
        "step": "kbase", "status": "installing", "message": "Installing KBase + Python 3.12..."
    }));

    let mut child = Command::new(&uv)
        .args(["tool", "install", "kbase-app", "--python", "3.12", "--force"])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start uv: {}", e))?;

    // Stream stderr for progress
    if let Some(stderr) = child.stderr.take() {
        let app_clone = app.clone();
        tokio::spawn(async move {
            let reader = BufReader::new(stderr);
            let mut lines = reader.lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let _ = app_clone.emit("setup-progress", serde_json::json!({
                    "step": "kbase", "status": "installing", "message": line
                }));
            }
        });
    }

    let status = child.wait().await.map_err(|e| format!("uv failed: {}", e))?;
    if !status.success() {
        return Err("kbase-app installation failed".to_string());
    }

    let _ = app.emit("setup-progress", serde_json::json!({
        "step": "done", "status": "complete", "message": "Installation complete!"
    }));

    Ok(())
}

// ── Start server ───────────────────────────────────────────────────

async fn start_python_server() -> Option<Child> {
    let python = find_python()?;

    let child = Command::new(&python)
        .args(["-m", "kbase.cli", "web", "--port", &PORT.to_string()])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .ok()?;

    Some(child)
}

// ── Tauri commands (callable from frontend JS) ─────────────────────

#[tauri::command]
async fn get_server_url() -> String {
    format!("http://{}:{}", HOST, PORT)
}

#[tauri::command]
async fn check_python_ready() -> bool {
    find_python().is_some()
}

#[tauri::command]
async fn run_setup(app: tauri::AppHandle) -> Result<String, String> {
    run_online_setup(app).await?;
    Ok("ok".to_string())
}

// ── Main ───────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(PythonProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_server_url,
            check_python_ready,
            run_setup,
        ])
        .setup(|app| {
            let handle = app.handle().clone();

            // Tray
            let open_item = MenuItem::with_id(app, "open", "Open KBase", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit KBase", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

            TrayIconBuilder::new()
                .tooltip("KBase")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "open" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            // Background: check Python → setup or start server
            let app_handle = handle.clone();
            tauri::async_runtime::spawn(async move {
                let already_running = is_server_running().await;

                if already_running {
                    // Server already up — just navigate
                    navigate_to_server(&app_handle).await;
                    return;
                }

                let python_ready = find_python().is_some();

                if python_ready {
                    // Python found — start server
                    start_and_navigate(&app_handle).await;
                } else {
                    // No Python — show setup UI, let frontend handle install
                    if let Some(w) = app_handle.get_webview_window("main") {
                        let _ = w.show();
                    }
                    // Frontend will call run_setup(), then we start server
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| match event {
            RunEvent::WindowEvent {
                label,
                event: WindowEvent::CloseRequested { api, .. },
                ..
            } if label == "main" => {
                api.prevent_close();
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
            RunEvent::ExitRequested { .. } => {
                if let Some(state) = app.try_state::<PythonProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.start_kill();
                    }
                }
            }
            _ => {}
        });
}

async fn start_and_navigate(app: &tauri::AppHandle) {
    if let Some(child) = start_python_server().await {
        if let Some(state) = app.try_state::<PythonProcess>() {
            *state.0.lock().unwrap() = Some(child);
        }
    }
    if wait_for_server(30).await {
        navigate_to_server(app).await;
    }
}

async fn navigate_to_server(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let url = format!("http://{}:{}/", HOST, PORT);
        let _ = w.eval(&format!("window.location.replace('{}')", url));
        let _ = w.show();
    }
}
