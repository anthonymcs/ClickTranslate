import React, { useState, useEffect, useRef, useCallback } from "react";
import mascotImg from "../assets/mascot.jpg";
import {
  Copy,
  Download,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Sparkles,
  ClipboardPaste,
  Check,
  AlertTriangle,
  Zap,
  RefreshCw
} from "lucide-react";

interface ClipboardViewProps {
  sourceLang: string;
  targetLang: string;
  selectedModel: string;
  createManagedUrl: (blob: Blob) => string;
  revokeManagedUrl: (url: string | null | undefined) => void;
  onClearMemoryTrigger: () => void;
}

export const ClipboardView: React.FC<ClipboardViewProps> = ({
  sourceLang,
  targetLang,
  selectedModel,
  createManagedUrl,
  revokeManagedUrl,
}) => {
  const [originalBlob, setOriginalBlob] = useState<Blob | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [translatedBlob, setTranslatedBlob] = useState<Blob | null>(null);
  const [translatedUrl, setTranslatedUrl] = useState<string | null>(null);

  const [isTranslating, setIsTranslating] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Estados de Zoom y Pan (Sincronizados)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Procesa una imagen Blob enviándola a /translate-single
  const processImageBlob = useCallback(
    async (blob: Blob) => {
      // Limpiar URLs previas
      if (originalUrl) revokeManagedUrl(originalUrl);
      if (translatedUrl) revokeManagedUrl(translatedUrl);

      const newOrigUrl = createManagedUrl(blob);
      setOriginalBlob(blob);
      setOriginalUrl(newOrigUrl);
      setTranslatedBlob(null);
      setTranslatedUrl(null);
      setErrorMessage(null);
      setCopied(false);
      setIsTranslating(true);
      setProgressPercent(15);

      // Progreso fluido de la barra de carga
      const p1 = setTimeout(() => setProgressPercent(45), 200);
      const p2 = setTimeout(() => setProgressPercent(75), 500);
      const p3 = setTimeout(() => setProgressPercent(90), 800);

      try {
        const formData = new FormData();
        formData.append("file", blob, "clipboard_image.png");
        formData.append("src_lang", sourceLang);
        formData.append("tgt_lang", targetLang);
        formData.append("model_name", selectedModel);

        const response = await fetch("http://127.0.0.1:8000/translate-single", {
          method: "POST",
          body: formData,
        });

        clearTimeout(p1);
        clearTimeout(p2);
        clearTimeout(p3);

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText || `Error del servidor (${response.status})`);
        }

        const outBlob = await response.blob();
        const newTransUrl = createManagedUrl(outBlob);

        setProgressPercent(100);
        setTimeout(() => {
          setTranslatedBlob(outBlob);
          setTranslatedUrl(newTransUrl);
          setIsTranslating(false);
        }, 150);
      } catch (err: any) {
        clearTimeout(p1);
        clearTimeout(p2);
        clearTimeout(p3);
        console.error("Error al traducir imagen:", err);
        setIsTranslating(false);
        const rawMsg = err?.message || "";
        if (rawMsg.includes("Failed to fetch") || rawMsg.includes("NetworkError")) {
          setErrorMessage("No se pudo conectar con el motor local (puerto 8000). Esperando al servidor...");
        } else {
          setErrorMessage(rawMsg || "Ocurrió un error al procesar la imagen en el backend.");
        }
      }
    },
    [sourceLang, targetLang, selectedModel, createManagedUrl, revokeManagedUrl, originalUrl, translatedUrl]
  );

  // Escuchar evento global 'paste' (Ctrl + V)
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image") !== -1) {
          const file = items[i].getAsFile();
          if (file) {
            e.preventDefault();
            processImageBlob(file);
            break;
          }
        }
      }
    };

    window.addEventListener("paste", handlePaste);
    return () => window.removeEventListener("paste", handlePaste);
  }, [processImageBlob]);

  // Manejo de Pan & Zoom con Mouse
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    setScale((prev) => Math.min(Math.max(prev * zoomFactor, 0.4), 6));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setOffset({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const resetView = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  };

  // Copiar imagen traducida al Portapapeles
  const copyToClipboard = async () => {
    if (!translatedBlob) return;
    try {
      const item = new ClipboardItem({ "image/png": translatedBlob });
      await navigator.clipboard.write([item]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Error al copiar al portapapeles:", err);
      downloadTranslatedImage();
    }
  };

  // Descarga directa en memoria
  const downloadTranslatedImage = () => {
    if (!translatedUrl) return;
    const a = document.createElement("a");
    a.href = translatedUrl;
    a.download = `ClickTranslate_${targetLang.toUpperCase()}_${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Arrastre manual de archivo
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith("image/")) {
        processImageBlob(file);
      }
    }
  };

  return (
    <div
      className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-background"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      {/* Barra de Estado con Barra de Carga Dinámica */}
      <div className="h-11 px-4 border-b border-surfaceBorder bg-surface/60 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          {/* Barra de Progreso Dinámica al traducir */}
          {isTranslating ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
                <Sparkles className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                <span>Traduciendo viñetas...</span>
              </div>
              <div className="w-48 bg-zinc-900 border border-zinc-700/80 rounded-full h-2.5 overflow-hidden p-0.5 shadow-inner">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 transition-all duration-300 ease-out shadow-sm shadow-indigo-500/50"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="font-mono text-xs text-cyan-300 font-bold">{progressPercent}%</span>
            </div>
          ) : errorMessage ? (
            <div className="flex items-center gap-2 text-rose-400 font-medium">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>{errorMessage}</span>
              {originalBlob && (
                <button
                  onClick={() => processImageBlob(originalBlob)}
                  className="px-2 py-0.5 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 font-semibold text-[11px] transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <RefreshCw className="w-2.5 h-2.5" />
                  <span>Reintentar</span>
                </button>
              )}
            </div>
          ) : translatedUrl ? (
            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <Check className="w-3.5 h-3.5" />
              <span>Traducción completada con éxito</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-zinc-400">
              <ClipboardPaste className="w-3.5 h-3.5 text-indigo-400" />
              <span>
                Presiona <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 font-mono">Ctrl + V</kbd> para traducir una captura al instante
              </span>
            </div>
          )}
        </div>

        {/* Herramientas de Pan & Zoom y Acciones */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-zinc-900 px-2 py-1 rounded-md border border-surfaceBorder gap-1.5">
            <button
              onClick={() => setScale((s) => Math.max(s * 0.85, 0.4))}
              title="Reducir Zoom"
              className="p-1 hover:text-white text-zinc-400 transition-colors"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[11px] font-mono text-zinc-300 w-11 text-center">
              {Math.round(scale * 100)}%
            </span>
            <button
              onClick={() => setScale((s) => Math.min(s * 1.15, 6))}
              title="Aumentar Zoom"
              className="p-1 hover:text-white text-zinc-400 transition-colors"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={resetView}
              title="Restablecer Vista"
              className="p-1 hover:text-white text-zinc-400 transition-colors ml-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          {translatedUrl && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={copyToClipboard}
                className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs shadow-sm transition-all active:scale-95"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-300" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? "¡Copiado!" : "Copiar"}</span>
              </button>
              <button
                onClick={downloadTranslatedImage}
                title="Descargar imagen PNG"
                className="p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Contenedor Principal: Vista Dividida (Original vs Traducido) */}
      <div
        className="flex-1 grid grid-cols-2 divide-x divide-surfaceBorder overflow-hidden relative select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
        style={{ cursor: isDragging ? "grabbing" : "grab" }}
      >
        {/* Panel Izquierdo: Original */}
        <div className="relative flex flex-col items-center justify-center h-full overflow-hidden bg-zinc-950/40 p-4">
          <div className="absolute top-3 left-4 z-10 px-2.5 py-1 rounded-md bg-zinc-900/80 backdrop-blur border border-surfaceBorder text-[11px] font-semibold text-zinc-300">
            Original {sourceLang !== "auto" ? `(${sourceLang.toUpperCase()})` : ""}
          </div>

          {originalUrl ? (
            <div
              className="origin-center transition-transform duration-75 ease-out select-none"
              style={{
                transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
              }}
            >
              <img
                src={originalUrl}
                alt="Página Original"
                className="max-h-[85vh] max-w-full object-contain rounded shadow-2xl pointer-events-none"
                draggable={false}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center text-center max-w-sm pointer-events-none p-6">
              <div className="relative mb-4 group">
                <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl blur-sm opacity-50" />
                <div className="relative w-24 h-24 rounded-2xl overflow-hidden border border-indigo-400/40 bg-zinc-900 shadow-xl">
                  <img
                    src={mascotImg}
                    alt="ClickTranslate"
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute bottom-1 right-1 bg-black/80 px-1.5 py-0.5 rounded text-[9px] font-bold text-indigo-300">
                    Ctrl+V
                  </div>
                </div>
              </div>

              <h3 className="text-base font-bold text-zinc-100 mb-1 flex items-center gap-2">
                <span>Captura o Pega tu Cómic</span>
              </h3>
              <p className="text-xs text-zinc-400 mb-4 leading-relaxed">
                Toma una captura con <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 font-mono text-[11px]">Win + Shift + S</kbd> y pulsa <kbd className="px-1.5 py-0.5 rounded bg-indigo-900/60 border border-indigo-500/40 text-indigo-300 font-mono text-[11px]">Ctrl + V</kbd> aquí.
              </p>

              {/* Badges de Formatos Soportados */}
              <div className="flex flex-wrap items-center justify-center gap-1.5 text-[10px] text-zinc-400">
                <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800">🇯🇵 Manga (RTL)</span>
                <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800">🇰🇷 Manhwa</span>
                <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800">🇨🇳 Manhua</span>
                <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800">🇺🇸 Comics (LTR)</span>
              </div>
            </div>
          )}
        </div>

        {/* Panel Derecho: Traducido */}
        <div className="relative flex flex-col items-center justify-center h-full overflow-hidden bg-zinc-950/20 p-4">
          <div className="absolute top-3 left-4 z-10 px-2.5 py-1 rounded-md bg-zinc-900/80 backdrop-blur border border-surfaceBorder text-[11px] font-semibold text-indigo-300 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-indigo-400" />
            Traducido ({targetLang.toUpperCase()})
          </div>

          {translatedUrl ? (
            <div
              className="origin-center transition-transform duration-75 ease-out select-none"
              style={{
                transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
              }}
            >
              <img
                src={translatedUrl}
                alt="Página Traducida"
                className="max-h-[85vh] max-w-full object-contain rounded shadow-2xl pointer-events-none"
                draggable={false}
              />
            </div>
          ) : isTranslating ? (
            /* Barra de Progreso Central Futurista con Porcentaje */
            <div className="flex flex-col items-center text-center max-w-xs pointer-events-none p-6">
              <div className="relative w-20 h-20 mb-4 flex items-center justify-center">
                <div className="absolute inset-0 rounded-full border-4 border-indigo-500/20 border-t-indigo-400 border-r-cyan-400 animate-spin" />
                <span className="font-mono text-lg font-extrabold text-white tracking-wider">
                  {progressPercent}%
                </span>
              </div>

              <p className="text-sm font-bold text-zinc-100 mb-1">Traduciendo viñetas...</p>
              <div className="w-56 bg-zinc-900 border border-zinc-800 rounded-full h-2 overflow-hidden mt-2 mb-1.5 shadow-inner">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 transition-all duration-300 ease-out"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-400 mt-1">Limpieza visual e inpainting en RAM</p>
            </div>
          ) : errorMessage && originalBlob ? (
            <div className="flex flex-col items-center text-center max-w-sm p-6 bg-rose-950/20 border border-rose-500/30 rounded-2xl shadow-xl">
              <div className="w-14 h-14 rounded-full bg-rose-500/20 border border-rose-500/30 flex items-center justify-center mb-3 text-rose-400">
                <AlertTriangle className="w-7 h-7" />
              </div>
              <p className="text-sm font-bold text-rose-200 mb-1">Error de conexión / traducción</p>
              <p className="text-xs text-rose-300/80 mb-4 leading-relaxed">
                {errorMessage}
              </p>
              <button
                onClick={() => processImageBlob(originalBlob)}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold text-xs shadow-lg shadow-indigo-500/25 transition-all flex items-center gap-2 cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reintentar Traducción</span>
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center text-center text-zinc-500 max-w-xs pointer-events-none p-6">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-3 text-indigo-400">
                <Sparkles className="w-8 h-8" />
              </div>
              <p className="text-sm font-semibold text-zinc-200 mb-1">Traducción Re-tipografiada</p>
              <p className="text-xs text-zinc-400 leading-relaxed">
                El motor detectará automáticamente globos de diálogo, limpiará el fondo y remaquetará el texto en <span className="font-semibold text-indigo-300">{targetLang.toUpperCase()}</span>.
              </p>
              <div className="mt-4 flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400">
                <Zap className="w-3 h-3 text-indigo-400" />
                <span>Zero-Persistence RAM: 100% Volátil</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
