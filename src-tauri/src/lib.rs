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
    // En Windows, si existe un proceso previo en el puerto 8000, reiniciarlo para asegurar backend fresco
    #[cfg(target_os = "windows")]
    {
        if std::net::TcpStream::connect("127.0.0.1:8000").is_ok() {
            println!("[Tauri] Proceso previo detectado en puerto 8000. Reiniciando backend limpio...");
            let _ = Command::new("powershell")
                .args(["-NoProfile", "-Command", "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"])
                .creation_flags(0x08000000)
                .status();
            std::thread::sleep(std::time::Duration::from_millis(400));
        }
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
            println!("[Tauri] Iniciando backend FastAPI automáticamente con {:?}", python_path);
            let mut cmd = Command::new(python_path);
            cmd.args(["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]);

            // Localizar el directorio que contiene 'main.py' subiendo en la jerarquía
            let mut backend_dir = None;
            let mut curr = python_path.parent();
            while let Some(dir) = curr {
                if dir.join("main.py").exists() {
                    backend_dir = Some(dir.to_path_buf());
                    break;
                }
                curr = dir.parent();
            }

            if backend_dir.is_none() {
                if let Ok(exe_path) = std::env::current_exe() {
                    if let Some(exe_dir) = exe_path.parent() {
                        let candidate_main = exe_dir.join("backend").join("main.py");
                        if candidate_main.exists() {
                            backend_dir = Some(exe_dir.join("backend"));
                        }
                    }
                }
            }

            if backend_dir.is_none() && PathBuf::from("backend/main.py").exists() {
                backend_dir = Some(PathBuf::from("backend"));
            }

            if let Some(ref dir) = backend_dir {
                println!("[Tauri] Directorio de ejecución del backend: {:?}", dir);
                cmd.current_dir(dir);
                cmd.env("PYTHONPATH", dir);

                // Redirigir stdout y stderr a backend.log para registro completo
                if let Ok(log_file) = std::fs::OpenOptions::new()
                    .create(true)
                    .write(true)
                    .truncate(true)
                    .open(dir.join("backend.log"))
                {
                    if let Ok(err_clone) = log_file.try_clone() {
                        cmd.stdout(log_file);
                        cmd.stderr(err_clone);
                    }
                }
            }

            #[cfg(target_os = "windows")]
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW (sin ventana de terminal)

            match cmd.spawn() {
                Ok(child) => {
                    let pid = child.id();
                    println!("[Tauri] Backend FastAPI iniciado con PID {}", pid);

                    // Esperar hasta 6 segundos a que el servidor FastAPI esté escuchando
                    for _ in 0..30 {
                        if std::net::TcpStream::connect("127.0.0.1:8000").is_ok() {
                            println!("[Tauri] ¡Conexión con FastAPI en http://127.0.0.1:8000 confirmada!");
                            break;
                        }
                        std::thread::sleep(std::time::Duration::from_millis(200));
                    }

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
                            println!("[Tauri] Cerrando proceso de backend PID {}...", child.id());
                            #[cfg(target_os = "windows")]
                            {
                                let pid_str = child.id().to_string();
                                let mut kill_cmd = Command::new("taskkill");
                                kill_cmd.args(["/F", "/T", "/PID", &pid_str]);
                                kill_cmd.creation_flags(0x08000000);
                                let _ = kill_cmd.status();
                            }
                            let _ = child.kill();
                        }
                    }
                }
                _ => {}
            }
        });
}
