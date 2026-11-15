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
  Image as ImageIcon,
  Check,
  AlertTriangle,
  Move,
  BookOpen,
  Zap
} from "lucide-react";

interface ClipboardViewProps {
  sourceLang: string;
  selectedModel: string;
  createManagedUrl: (blob: Blob) => string;
  revokeManagedUrl: (url: string | null | undefined) => void;
  onClearMemoryTrigger: () => void;
}

type Stage =
  | "idle"
  | "detecting"
  | "cleaning"
  | "translating"
  | "typesetting"
  | "done"
  | "error";

const STAGE_LABELS: Record<Stage, string> = {
  idle: "Listo",
  detecting: "Detectando globos y onomatopeyas...",
  cleaning: "Limpiando dibujo con LaMa y OpenCV...",
  translating: "Traduciendo contexto completo con Ollama...",
  typesetting: "Re-tipografiando fuentes...",
  done: "Traducción completada con éxito",
  error: "Error durante el procesamiento",
};

export const ClipboardView: React.FC<ClipboardViewProps> = ({
  sourceLang,
  selectedModel,
  createManagedUrl,
  revokeManagedUrl,
}) => {
  const [originalBlob, setOriginalBlob] = useState<Blob | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [translatedBlob, setTranslatedBlob] = useState<Blob | null>(null);
  const [translatedUrl, setTranslatedUrl] = useState<string | null>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Estados de Zoom y Pan (Sincronizados)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [syncPanZoom, setSyncPanZoom] = useState(true);

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

      // Simulación de etapas visuales para feedback al usuario
      setStage("detecting");
      const stageTimer1 = setTimeout(() => setStage("cleaning"), 500);
      const stageTimer2 = setTimeout(() => setStage("translating"), 1100);
      const stageTimer3 = setTimeout(() => setStage("typesetting"), 2200);

      try {
        const formData = new FormData();
        formData.append("file", blob, "clipboard_image.png");
        formData.append("src_lang", sourceLang);
        formData.append("model_name", selectedModel);

        const response = await fetch("http://127.0.0.1:8000/translate-single", {
          method: "POST",
          body: formData,
        });

        clearTimeout(stageTimer1);
        clearTimeout(stageTimer2);
        clearTimeout(stageTimer3);

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText || `Error del servidor (${response.status})`);
        }

        const outBlob = await response.blob();
        const newTransUrl = createManagedUrl(outBlob);

        setTranslatedBlob(outBlob);
        setTranslatedUrl(newTransUrl);
        setStage("done");
      } catch (err: any) {
        clearTimeout(stageTimer1);
        clearTimeout(stageTimer2);
        clearTimeout(stageTimer3);
        console.error("Error al traducir imagen:", err);
        setStage("error");
        setErrorMessage(err.message || "Ocurrió un error al procesar la imagen en el backend.");
      }
    },
    [sourceLang, selectedModel, createManagedUrl, revokeManagedUrl, originalUrl, translatedUrl]
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
      // Click izquierdo para arrastrar
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

  // Copiar imagen traducida al Portapapeles (navigator.clipboard.write)
  const copyToClipboard = async () => {
    if (!translatedBlob) return;
    try {
      // El portapapeles requiere PNG estricto
      const item = new ClipboardItem({ "image/png": translatedBlob });
      await navigator.clipboard.write([item]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Error al copiar al portapapeles:", err);
      // Fallback: descargar
      downloadTranslatedImage();
    }
  };

  // Descarga directa en memoria
  const downloadTranslatedImage = () => {
    if (!translatedUrl) return;
    const a = document.createElement("a");
    a.href = translatedUrl;
    a.download = `ClickTranslate_${Date.now()}.png`;
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

  const isBusy = ["detecting", "cleaning", "translating", "typesetting"].includes(stage);

  return (
    <div
      className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-background"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      {/* Barra de Estado y Controles de Vista */}
      <div className="h-11 px-4 border-b border-surfaceBorder bg-surface/60 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          {/* Indicador de Etapa Actual */}
          {isBusy ? (
            <div className="flex items-center gap-2 text-indigo-400 font-medium">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
              <span>{STAGE_LABELS[stage]}</span>
            </div>
          ) : stage === "done" ? (
            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <Check className="w-3.5 h-3.5" />
              <span>{STAGE_LABELS.done}</span>
            </div>
          ) : stage === "error" ? (
            <div className="flex items-center gap-1.5 text-rose-400 font-medium">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{errorMessage || STAGE_LABELS.error}</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-zinc-400">
              <ClipboardPaste className="w-3.5 h-3.5 text-indigo-400" />
              <span>Presiona <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 font-mono">Ctrl + V</kbd> para traducir una captura al instante</span>
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
            Original
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
                <span>Captura o Pega tu Manga</span>
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
            Traducido (ES)
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
          ) : isBusy ? (
            <div className="flex flex-col items-center text-center text-indigo-400 pointer-events-none">
              <div className="w-14 h-14 rounded-full border-2 border-indigo-500/20 border-t-indigo-500 animate-spin mb-4" />
              <p className="text-sm font-medium text-zinc-200">{STAGE_LABELS[stage]}</p>
              <p className="text-xs text-zinc-500 mt-1">Procesando estrictamente en memoria RAM</p>
            </div>
          ) : (
            <div className="flex flex-col items-center text-center text-zinc-500 max-w-xs pointer-events-none p-6">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-3 text-indigo-400">
                <Sparkles className="w-8 h-8" />
              </div>
              <p className="text-sm font-semibold text-zinc-200 mb-1">Traducción Re-tipografiada</p>
              <p className="text-xs text-zinc-400 leading-relaxed">
                El motor detectará automáticamente globos y onomatopeyas, limpiará el fondo con LaMa y maquetará la traducción en español.
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
