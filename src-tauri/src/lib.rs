use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

struct BackendState(Mutex<Option<Child>>);

fn spawn_ollama_if_needed() {
    if std::net::TcpStream::connect("127.0.0.1:11434").is_ok() {
        return;
    }

    let mut candidates = vec![PathBuf::from("ollama")];
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        candidates.push(PathBuf::from(local_app_data).join(r"Programs\Ollama\ollama.exe"));
    }

    for ollama_path in candidates {
        let mut cmd = Command::new(&ollama_path);
        cmd.arg("serve");
        #[cfg(target_os = "windows")]
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        if cmd.spawn().is_ok() {
            println!("[Tauri] Ollama iniciado automáticamente: {:?}", ollama_path);
            break;
        }
    }
}

fn spawn_backend_if_needed() -> Option<Child> {
    // Verificar si el backend ya está activo en http://127.0.0.1:8000
    if std::net::TcpStream::connect("127.0.0.1:8000").is_ok() {
        println!("[Tauri] Backend FastAPI ya detectado en http://127.0.0.1:8000");
        return None;
    }

    // Buscar el ejecutable de Python del venv de forma robusta
    let mut candidates = vec![
        PathBuf::from("backend/venv/Scripts/python.exe"),
        PathBuf::from("../backend/venv/Scripts/python.exe"),
        PathBuf::from("backend/venv/bin/python"),
        PathBuf::from("../backend/venv/bin/python"),
    ];

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("backend/venv/Scripts/python.exe"));
            candidates.push(exe_dir.join("../backend/venv/Scripts/python.exe"));
            candidates.push(exe_dir.join("../../backend/venv/Scripts/python.exe"));
            candidates.push(exe_dir.join("../../../backend/venv/Scripts/python.exe"));
        }
    }

    for python_path in &candidates {
        if python_path.exists() {
            println!("[Tauri] Iniciando backend FastAPI automáticamente: {:?}", python_path);
            let mut cmd = Command::new(python_path);
            cmd.args(["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]);

            if let Some(parent) = python_path.parent().and_then(|p| p.parent()) {
                cmd.current_dir(parent);
            }

            #[cfg(target_os = "windows")]
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW (oculta la ventana negra en Windows)

            match cmd.spawn() {
                Ok(child) => {
                    println!("[Tauri] Backend iniciado con PID {}", child.id());
                    return Some(child);
                }
                Err(err) => {
                    eprintln!("[Tauri] No se pudo iniciar el proceso de backend: {}", err);
                }
            }
            break;
        }
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .manage(BackendState(Mutex::new(None)))
        .setup(|app| {
            spawn_ollama_if_needed();
            let backend_child = spawn_backend_if_needed();
            let state = app.state::<BackendState>();
            if let Ok(mut lock) = state.0.lock() {
                *lock = backend_child;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                    if let Some(state) = app_handle.try_state::<BackendState>() {
                        let mut child_opt = None;
                        if let Ok(mut lock) = state.0.lock() {
                            child_opt = lock.take();
                        }
                        if let Some(mut child) = child_opt {
                            println!("[Tauri] Cerrando proceso de backend...");
                            let _ = child.kill();
                        }
                    }
                }
                _ => {}
            }
        });
}
