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
  RefreshCw,
  X,
  Upload,
  Columns,
  Image as ImageIcon,
  Eye
} from "lucide-react";

interface ClipboardViewProps {
  sourceLang: string;
  targetLang: string;
  selectedModel: string;
  createManagedUrl: (blob: Blob) => string;
  revokeManagedUrl: (url: string | null | undefined) => void;
  onClearMemoryTrigger: () => void;
}

type ViewLayout = "split" | "translated" | "original";

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

  const [viewLayout, setViewLayout] = useState<ViewLayout>("split");
  const [isTranslating, setIsTranslating] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const lastParamsRef = useRef({ sourceLang, targetLang, selectedModel });

  // Estados de Zoom y Pan (Sincronizados)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Quitar imagen actual (Botón X estilo Google Translate)
  const clearCurrentImage = useCallback(() => {
    if (originalUrl) revokeManagedUrl(originalUrl);
    if (translatedUrl) revokeManagedUrl(translatedUrl);
    setOriginalBlob(null);
    setOriginalUrl(null);
    setTranslatedBlob(null);
    setTranslatedUrl(null);
    setErrorMessage(null);
    setIsTranslating(false);
    setProgressPercent(0);
    setCopied(false);
    setScale(1);
    setOffset({ x: 0, y: 0 });
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [originalUrl, translatedUrl, revokeManagedUrl]);

  // Procesa una imagen Blob enviándola a /translate-single
  const processImageBlob = useCallback(
    async (blob: Blob, keepOriginalUrl = false) => {
      if (!keepOriginalUrl) {
        if (originalUrl) revokeManagedUrl(originalUrl);
        const newOrigUrl = createManagedUrl(blob);
        setOriginalBlob(blob);
        setOriginalUrl(newOrigUrl);
        setScale(1);
        setOffset({ x: 0, y: 0 });
      }
      if (translatedUrl) revokeManagedUrl(translatedUrl);

      setTranslatedBlob(null);
      setTranslatedUrl(null);
      setErrorMessage(null);
      setCopied(false);
      setIsTranslating(true);
      setProgressPercent(18);

      const p1 = setTimeout(() => setProgressPercent(48), 180);
      const p2 = setTimeout(() => setProgressPercent(78), 450);
      const p3 = setTimeout(() => setProgressPercent(92), 800);

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
        }, 100);
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

  // Re-traducir automáticamente si el usuario cambia idioma o modelo de IA con una imagen cargada
  useEffect(() => {
    const prev = lastParamsRef.current;
    const changed =
      prev.sourceLang !== sourceLang ||
      prev.targetLang !== targetLang ||
      prev.selectedModel !== selectedModel;
    lastParamsRef.current = { sourceLang, targetLang, selectedModel };

    if (changed && originalBlob && !isTranslating) {
      processImageBlob(originalBlob, true);
    }
  }, [sourceLang, targetLang, selectedModel, originalBlob, isTranslating, processImageBlob]);

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

  // Botón para pegar directamente desde el portapapeles (estilo Google Translate)
  const handlePasteFromButton = async () => {
    try {
      if (!navigator.clipboard || !navigator.clipboard.read) {
        return;
      }
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const imageType = item.types.find((t) => t.startsWith("image/"));
        if (imageType) {
          const blob = await item.getType(imageType);
          processImageBlob(blob);
          return;
        }
      }
    } catch (err) {
      console.warn("Usa Ctrl+V para pegar directamente:", err);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith("image/")) {
      processImageBlob(file);
    }
  };

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
    setIsDragOver(false);
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
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Barra Superior de Herramientas (Estilo Google Translate Imágenes) */}
      <div className="h-12 px-4 border-b border-surfaceBorder bg-surface/75 backdrop-blur flex items-center justify-between text-xs z-20">
        <div className="flex items-center gap-3">
          {isTranslating ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
                <Sparkles className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                <span>Traduciendo con IA...</span>
              </div>
              <div className="w-44 bg-zinc-900 border border-zinc-700/80 rounded-full h-2.5 overflow-hidden p-0.5 shadow-inner">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 transition-all duration-300 ease-out"
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
                  onClick={() => processImageBlob(originalBlob, true)}
                  className="px-2.5 py-1 rounded-md bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 font-semibold text-[11px] transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Reintentar</span>
                </button>
              )}
            </div>
          ) : originalUrl ? (
            /* Selector de Vista estilo Google Translate (Mostrar original / Lado a lado / Traducido) */
            <div className="flex items-center gap-2">
              <div className="flex items-center bg-zinc-900/90 p-0.5 rounded-lg border border-surfaceBorder">
                <button
                  onClick={() => setViewLayout("split")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
                    viewLayout === "split"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <Columns className="w-3.5 h-3.5" />
                  <span>Lado a lado</span>
                </button>
                <button
                  onClick={() => setViewLayout("translated")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
                    viewLayout === "translated"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Solo Traducido</span>
                </button>
                <button
                  onClick={() => setViewLayout("original")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
                    viewLayout === "original"
                      ? "bg-zinc-700 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>Original</span>
                </button>
              </div>

              {translatedUrl && (
                <span className="hidden sm:inline-flex items-center gap-1 text-emerald-400 font-medium ml-1">
                  <Check className="w-3.5 h-3.5" />
                  <span>Listo</span>
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-zinc-400">
              <ClipboardPaste className="w-3.5 h-3.5 text-indigo-400" />
              <span>
                Pega una imagen con{" "}
                <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 font-mono">
                  Ctrl + V
                </kbd>{" "}
                o arrastra un archivo
              </span>
            </div>
          )}
        </div>

        {/* Acciones Derecha: Zoom + Copiar + Descargar + Botón X (Cerrar imagen actual) */}
        {originalUrl && (
          <div className="flex items-center gap-2">
            {/* Zoom Controls */}
            <div className="flex items-center bg-zinc-900 px-2 py-1 rounded-lg border border-surfaceBorder gap-1">
              <button
                onClick={() => setScale((s) => Math.max(s * 0.85, 0.4))}
                title="Reducir Zoom"
                className="p-1 hover:text-white text-zinc-400 transition-colors cursor-pointer"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-[11px] font-mono text-zinc-300 w-11 text-center">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(s * 1.15, 6))}
                title="Aumentar Zoom"
                className="p-1 hover:text-white text-zinc-400 transition-colors cursor-pointer"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={resetView}
                title="Restablecer Zoom"
                className="p-1 hover:text-white text-zinc-400 transition-colors ml-0.5 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>

            {originalBlob && !isTranslating && (
              <button
                onClick={() => processImageBlob(originalBlob, true)}
                title="Volver a traducir con el idioma/modelo actual"
                className="p-1.5 rounded-lg bg-zinc-800/90 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700/60 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}

            {translatedUrl && (
              <>
                <button
                  onClick={copyToClipboard}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-sm transition-all active:scale-95 cursor-pointer"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-300" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  <span>{copied ? "¡Copiada!" : "Copiar imagen"}</span>
                </button>
                <button
                  onClick={downloadTranslatedImage}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-100 border border-zinc-700 font-medium text-xs transition-colors cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Descargar</span>
                </button>
              </>
            )}

            {/* Botón X estilo Google Translate para cerrar/quitar la imagen actual */}
            <button
              onClick={clearCurrentImage}
              title="Quitar imagen actual (Cerrar)"
              className="flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-800/90 hover:bg-rose-500/20 text-zinc-300 hover:text-rose-300 border border-zinc-700 hover:border-rose-500/40 transition-all cursor-pointer ml-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Área Principal */}
      {!originalUrl ? (
        /* Estado Vacío: Tarjeta estilo Google Translate Imágenes */
        <div className="flex-1 flex items-center justify-center p-6">
          <div
            className={`w-full max-w-2xl rounded-3xl border-2 border-dashed transition-all p-10 flex flex-col items-center text-center shadow-2xl ${
              isDragOver
                ? "border-indigo-400 bg-indigo-950/30 scale-[1.01]"
                : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700"
            }`}
          >
            <div className="relative mb-5">
              <div className="absolute -inset-1.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 rounded-2xl blur opacity-40" />
              <div className="relative w-24 h-24 rounded-2xl overflow-hidden border border-indigo-400/40 bg-zinc-900 shadow-xl">
                <img
                  src={mascotImg}
                  alt="ClickTranslate"
                  className="w-full h-full object-cover"
                />
              </div>
            </div>

            <h2 className="text-lg font-bold text-zinc-100 mb-1.5">
              Arrastra una imagen aquí o pégala desde el portapapeles
            </h2>
            <p className="text-xs text-zinc-400 mb-6 max-w-md leading-relaxed">
              Toma un recorte con{" "}
              <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 font-mono text-[11px]">
                Win + Shift + S
              </kbd>{" "}
              y presiona{" "}
              <kbd className="px-1.5 py-0.5 rounded bg-indigo-950 border border-indigo-500/40 text-indigo-300 font-mono text-[11px]">
                Ctrl + V
              </kbd>{" "}
              en cualquier momento para traducir y limpiar globos automáticamente.
            </p>

            {/* Botones principales estilo Google Translate: Explorar archivos + Pegar del portapapeles */}
            <div className="flex flex-wrap items-center justify-center gap-3 mb-6">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/25 transition-all active:scale-95 cursor-pointer"
              >
                <Upload className="w-4 h-4" />
                <span>Explorar archivos</span>
              </button>

              <button
                onClick={handlePasteFromButton}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-100 border border-zinc-700 font-semibold text-xs transition-all active:scale-95 cursor-pointer"
              >
                <ClipboardPaste className="w-4 h-4 text-indigo-400" />
                <span>Pegar del portapapeles (Ctrl+V)</span>
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2 text-[11px] text-zinc-400">
              <span className="px-2.5 py-1 rounded-full bg-zinc-900/90 border border-zinc-800">
                🇯🇵 Manga (Vertical / Horizontal)
              </span>
              <span className="px-2.5 py-1 rounded-full bg-zinc-900/90 border border-zinc-800">
                🇰🇷 Manhwa / Webtoon
              </span>
              <span className="px-2.5 py-1 rounded-full bg-zinc-900/90 border border-zinc-800">
                🇨🇳 Manhua
              </span>
              <span className="px-2.5 py-1 rounded-full bg-zinc-900/90 border border-zinc-800">
                🔞 Sin Censura (PNG / JPG / WEBP)
              </span>
            </div>
          </div>
        </div>
      ) : (
        /* Visor de Imagen Cargada con Botón X Flotante estilo Google Translate */
        <div
          className={`flex-1 grid ${
            viewLayout === "split" ? "grid-cols-2 divide-x divide-surfaceBorder" : "grid-cols-1"
          } overflow-hidden relative select-none`}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onWheel={handleWheel}
          style={{ cursor: isDragging ? "grabbing" : "grab" }}
        >
          {/* Botón X flotante en la esquina superior derecha del lienzo (como en Google Translate Imágenes) */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              clearCurrentImage();
            }}
            title="Cerrar imagen y subir otra"
            className="absolute top-3 right-4 z-30 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-900/90 hover:bg-rose-600 text-zinc-200 hover:text-white border border-zinc-700 hover:border-rose-500 shadow-xl backdrop-blur transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
            <span className="text-xs font-semibold">Quitar imagen</span>
          </button>

          {/* Panel Original */}
          {(viewLayout === "split" || viewLayout === "original") && (
            <div className="relative flex flex-col items-center justify-center h-full overflow-hidden bg-zinc-950/40 p-4">
              <div className="absolute top-3 left-4 z-10 px-2.5 py-1 rounded-md bg-zinc-900/85 backdrop-blur border border-surfaceBorder text-[11px] font-semibold text-zinc-300 flex items-center gap-1.5">
                <ImageIcon className="w-3 h-3 text-zinc-400" />
                <span>Original {sourceLang !== "auto" ? `(${sourceLang.toUpperCase()})` : ""}</span>
              </div>

              <div
                className="origin-center transition-transform duration-75 ease-out select-none"
                style={{
                  transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
                }}
              >
                <img
                  src={originalUrl}
                  alt="Página Original"
                  className="max-h-[84vh] max-w-full object-contain rounded shadow-2xl pointer-events-none"
                  draggable={false}
                />
              </div>
            </div>
          )}

          {/* Panel Traducido */}
          {(viewLayout === "split" || viewLayout === "translated") && (
            <div className="relative flex flex-col items-center justify-center h-full overflow-hidden bg-zinc-950/20 p-4">
              <div className="absolute top-3 left-4 z-10 px-2.5 py-1 rounded-md bg-zinc-900/85 backdrop-blur border border-surfaceBorder text-[11px] font-semibold text-indigo-300 flex items-center gap-1.5">
                <Sparkles className="w-3 h-3 text-indigo-400" />
                <span>Traducido ({targetLang.toUpperCase()})</span>
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
                    className="max-h-[84vh] max-w-full object-contain rounded shadow-2xl pointer-events-none"
                    draggable={false}
                  />
                </div>
              ) : isTranslating ? (
                <div className="flex flex-col items-center text-center max-w-xs pointer-events-none p-6">
                  <div className="relative w-20 h-20 mb-4 flex items-center justify-center">
                    <div className="absolute inset-0 rounded-full border-4 border-indigo-500/20 border-t-indigo-400 border-r-cyan-400 animate-spin" />
                    <span className="font-mono text-lg font-extrabold text-white tracking-wider">
                      {progressPercent}%
                    </span>
                  </div>

                  <p className="text-sm font-bold text-zinc-100 mb-1">
                    Limpiando globos y traduciendo...
                  </p>
                  <div className="w-56 bg-zinc-900 border border-zinc-800 rounded-full h-2 overflow-hidden mt-2 mb-1.5 shadow-inner">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 transition-all duration-300 ease-out"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-1">
                    Reconstrucción tipográfica tipo Scanlation
                  </p>
                </div>
              ) : errorMessage && originalBlob ? (
                <div className="flex flex-col items-center text-center max-w-sm p-6 bg-rose-950/20 border border-rose-500/30 rounded-2xl shadow-xl">
                  <div className="w-14 h-14 rounded-full bg-rose-500/20 border border-rose-500/30 flex items-center justify-center mb-3 text-rose-400">
                    <AlertTriangle className="w-7 h-7" />
                  </div>
                  <p className="text-sm font-bold text-rose-200 mb-1">
                    Error de conexión / traducción
                  </p>
                  <p className="text-xs text-rose-300/80 mb-4 leading-relaxed">{errorMessage}</p>
                  <button
                    onClick={() => processImageBlob(originalBlob, true)}
                    className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold text-xs shadow-lg shadow-indigo-500/25 transition-all flex items-center gap-2 cursor-pointer"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Reintentar Traducción</span>
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
