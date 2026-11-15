# ClickTranslate ⚡📖

Herramienta de escritorio moderna y ultrarrápida especializada en la **traducción visual de mangas, manhwas, manhuas y cómics occidentales**, impulsada por modelos locales de IA y diseñada bajo el principio estricto de **Cero Persistencia en Disco** (100% en memoria RAM).

![ClickTranslate UI](https://raw.githubusercontent.com/anthonymcs/ClickTranslate/main/docs/preview.png)

---

## 🌟 Características Principales

* 🚀 **Principio de Cero Persistencia (Zero-Persistence):**
  Tanto las capturas individuales del portapapeles como los capítulos enteros (`.zip` / `.cbz`) se procesan, traducen y empaquetan **exclusivamente en memoria RAM** (`io.BytesIO`, `zipfile`, `Blob`, `URL.createObjectURL`). Nunca se escriben archivos temporales en el disco duro.

* 🧠 **Traducción Local con Ollama:**
  Integración asíncrona con Ollama local (`http://localhost:11434`) mediante contexto de página completa. Detecta automáticamente tus modelos instalados (ej. `qwen2.5:7b`, `gemma2:9b`). Incluye directiva `"keep_alive": "5m"` para liberar memoria RAM tras inactividad.

* 🎨 **Soporte Sin Restricciones Gráficas:**
  Diseñado para traducir con absoluta fidelidad cualquier obra sin censura ni bloqueos arbitrarios (Shonen, Seinen, Manhwa, Romance, Ecchi/Eromanga, Horror, Gore, etc.).

* ⚡ **Pipeline Visual Inteligente:**
  1. **Detección y Clasificación:** Diferenciación precisa entre globos de diálogo y onomatopeyas (`SFX`) sobre la ilustración, ordenando los bloques según el sentido de lectura (derecha a izquierda para Manga; izquierda a derecha para Manhwa/Cómics).
  2. **OCR Multi-idioma:** `Manga-OCR` para japonés vertical con furigana; `PaddleOCR` para coreano, chino e inglés.
  3. **Limpieza Visual Híbrida:** Relleno instantáneo OpenCV (< 5 ms) para globos lisos + red neuronal `LaMa` (`simple-lama-inpainting`) para reconstruir el arte original debajo de las onomatopeyas.
  4. **Re-tipografía Adaptativa:** Ajuste dinámico de tamaño de fuente (*auto-fit*) y *word-wrap* centrado en globos, y contornos contrastantes en onomatopeyas.

* 🗂️ **Dos Modos de Trabajo:**
  * **Modo Rápido (`Ctrl + V`):** Pega cualquier captura directamente de tu pantalla, visualiza la comparativa en paralelo con *Pan & Zoom* sincronizado y copia la imagen traducida al portapapeles con un clic.
  * **Lote Capítulo (`.ZIP` / `.CBZ`):** Arrastra y suelta un capítulo entero; observa el progreso en tiempo real con Server-Sent Events (SSE) y miniaturas en vivo, descargando el archivo final listo.

* 🧹 **Botón Limpiar RAM (`Esc`):**
  Atajo rápido para revocar al instante todas las URLs de blobs en el navegador y purgar buffers del sistema.

---

## 📁 Estructura del Repositorio

```
ClickTranslate/
├── src-tauri/                  # Configuración de Tauri v2 (Rust) y permisos
├── src/                        # Frontend React + TypeScript + Tailwind
│   ├── components/
│   │   ├── TopBar.tsx          # Controles de modo, idioma, modelo Ollama y botón limpiar
│   │   ├── ClipboardView.tsx   # Vista dividida (Original vs Traducido) con Ctrl+V
│   │   └── BatchZipView.tsx    # Drag & Drop de ZIP/CBZ, barra SSE y vista previa en vivo
│   ├── hooks/
│   │   └── useMemoryCleanup.ts # Gestión de URL.revokeObjectURL y liberación de RAM
│   └── App.tsx
├── backend/                    # Servidor Python FastAPI (Zero-Disk)
│   ├── assets/
│   │   └── fonts/              # Fuentes tipográficas (.ttf) para auto-fit
│   ├── core/
│   │   ├── detector.py         # Detección de globos vs SFX y orden de lectura
│   │   ├── ocr_engine.py       # Manga-OCR (JP) y PaddleOCR (KR, CN, EN)
│   │   ├── inpainter.py        # OpenCV rápido para globos + LaMa para SFX
│   │   ├── translator.py       # Cliente asíncrono Ollama con contexto de página
│   │   └── typesetter.py       # Auto-fit tipográfico y renderizado Pillow
│   ├── main.py                 # Endpoints FastAPI y SSE (/translate-single, /translate-batch)
│   └── requirements.txt
└── README.md
```

---

## 🛠️ Requisitos Previos

1. **Python 3.10 - 3.12** instalado en el sistema.
2. **Node.js (v18+)** y **Rust / Cargo** (para compilar Tauri v2).
3. **Ollama** ejecutándose localmente con al menos un modelo descargado:
   ```bash
   # Descargar e iniciar Ollama (https://ollama.com)
   ollama pull qwen2.5:7b
   # o bien: ollama pull gemma2:9b
   ```

---

## ⚡ Inicio Rápido con 1 Solo Clic (Recomendado)

¡No necesitas abrir consolas ni escribir comandos manualmente cada vez!

1. **Desde tu Escritorio:**
   * Haz doble clic en el acceso directo **`ClickTranslate`** creado en tu Escritorio de Windows.
2. **O desde la carpeta del proyecto:**
   * Haz doble clic en **`Iniciar ClickTranslate.bat`** (o en `ClickTranslate.vbs` para modo silencioso).

Este lanzador automático se encarga de:
* Iniciar Ollama en segundo plano (si aún no está activo).
* Levantar el servidor FastAPI sin ventanas molestas.
* Abrir la aplicación de escritorio de inmediato.
* Detener el backend y liberar toda la memoria RAM en cuanto cierras la aplicación.

Si deseas recrear el acceso directo en el Escritorio en cualquier momento, simplemente ejecuta `Crear Acceso Directo en Escritorio.bat`.

---

## 🚀 Instalación Manual (Opcional)

### 1. Clonar el Repositorio

```bash
git clone https://github.com/anthonymcs/ClickTranslate.git
cd ClickTranslate
```

### 2. Configurar el Backend (Python)

Crea un entorno virtual e instala las dependencias:

```bash
cd backend
python -m venv venv

# En Windows:
.\venv\Scripts\activate
# En Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

#### Fuentes Tipográficas Recomendadas

Coloca fuentes `.ttf` en `backend/assets/fonts/`:
* Diálogos: `AnimeAce.ttf` o `WildWords.ttf` (estándar de manga).
* Onomatopeyas: `Impact.ttf` o `Bangers.ttf`.

> *Nota:* Si la carpeta se encuentra vacía, ClickTranslate utilizará automáticamente las fuentes del sistema (Arial, Segoe UI, Tahoma) sin interrumpir el proceso.

#### Iniciar el Servidor Backend:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

El servidor estará escuchando en `http://127.0.0.1:8000`.

---

### 3. Configurar y Ejecutar la App de Escritorio (Tauri + React)

En una nueva terminal, en la raíz del proyecto:

```bash
# Instalar dependencias de Node
npm install

# Ejecutar la aplicación en modo desarrollo (Tauri v2 + Vite)
npm run tauri dev
```

O si deseas ejecutar únicamente la versión Web en el navegador:
```bash
npm run dev
```

---

## 💡 Flujo de Trabajo y Atajos

* **`Ctrl + V`:** Pega capturas de pantalla tomadas con `Win + Shift + S` para traducirlas de inmediato.
* **`Esc`:** Libera inmediatamente la memoria RAM y revoca todos los ObjectURLs activos.
* **Rueda del Ratón / Arrastre:** Control sincronizado de Zoom y desplazamiento entre el panel original y traducido.
* **Copiar:** Envía la imagen limpia y re-tipografiada directamente al portapapeles en formato PNG.

---

## 📄 Licencia

Desarrollado bajo licencia MIT por **Anthony Macias** ([@anthonymcs](https://github.com/anthonymcs)).
