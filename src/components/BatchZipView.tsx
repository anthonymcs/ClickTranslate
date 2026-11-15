import React, { useState, useEffect, useRef, useCallback } from "react";
import JSZip from "jszip";
import {
  UploadCloud,
  FileArchive,
  Download,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Copy,
  Check,
  Play,
  Pause,
  X,
  Layers,
  Image as ImageIcon,
  Columns,
  Maximize2
} from "lucide-react";

export interface BatchZipViewProps {
  sourceLang: string;
  targetLang: string;
  selectedModel: string;
  outputFormat: "zip" | "cbz";
  createManagedUrl: (blob: Blob) => string;
  revokeManagedUrl: (url: string | null | undefined) => void;
  onClearMemoryTrigger: () => void;
}

export interface PageItem {
  id: number;
  name: string;
  origBlob: Blob;
  origUrl: string;
  transBlob: Blob | null;
  transUrl: string | null;
  status: "idle" | "translating" | "done" | "error";
  errorMessage?: string;
}

function naturalCompare(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

export const BatchZipView: React.FC<BatchZipViewProps> = ({
  sourceLang,
  targetLang,
  selectedModel,
  outputFormat,
  createManagedUrl,
  revokeManagedUrl,
  onClearMemoryTrigger,
}) => {
  const [pages, setPages] = useState<PageItem[]>([]);
  const [activePageIndex, setActivePageIndex] = useState<number>(0);
  const [chapterTitle, setChapterTitle] = useState<string>("");
  const [isLoadingFiles, setIsLoadingFiles] = useState<boolean>(false);
  const [isQueueRunning, setIsQueueRunning] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Modos de Visualización: 'split' (lado a lado) o 'toggle' (superpuesto con alternancia)
  const [viewMode, setViewMode] = useState<"split" | "toggle">("split");
  const [toggleShowOriginal, setToggleShowOriginal] = useState<boolean>(false);

  // Estados de Zoom y Pan (Sincronizados)
  const [scale, setScale] = useState<number>(1);
  const [offset, setOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const isQueueRunningRef = useRef<boolean>(false);
  const pagesRef = useRef<PageItem[]>([]);
  pagesRef.current = pages;

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const thumbnailStripRef = useRef<HTMLDivElement | null>(null);

  // Limpiar memoria al desmontar
  useEffect(() => {
    return () => {
      isQueueRunningRef.current = false;
      pagesRef.current.forEach((p) => {
        revokeManagedUrl(p.origUrl);
        if (p.transUrl) revokeManagedUrl(p.transUrl);
      });
    };
  }, [revokeManagedUrl]);

  // Carga de Archivos (ZIP, CBZ o selección múltiple de imágenes)
  const handleFiles = async (fileList: FileList | File[]) => {
    if (!fileList || fileList.length === 0) return;
    setIsLoadingFiles(true);

    try {
      // Limpiar páginas previas
      pages.forEach((p) => {
        revokeManagedUrl(p.origUrl);
        if (p.transUrl) revokeManagedUrl(p.transUrl);
      });
      setPages([]);
      setActivePageIndex(0);

      const firstFile = fileList[0];
      const isZipOrCbz =
        firstFile.name.toLowerCase().endsWith(".zip") ||
        firstFile.name.toLowerCase().endsWith(".cbz");

      const newPages: PageItem[] = [];

      if (isZipOrCbz) {
        setChapterTitle(firstFile.name.replace(/\.[^/.]+$/, ""));
        const zip = await JSZip.loadAsync(firstFile);
        const entries: { path: string; entry: JSZip.JSZipObject }[] = [];

        zip.forEach((relPath, entry) => {
          if (
            !entry.dir &&
            !relPath.startsWith("__MACOSX/") &&
            !relPath.startsWith(".") &&
            /\.(png|jpe?g|webp)$/i.test(relPath)
          ) {
            entries.push({ path: relPath, entry });
          }
        });

        entries.sort((a, b) => naturalCompare(a.path, b.path));

        let idCounter = 1;
        for (const item of entries) {
          const blob = await item.entry.async("blob");
          const url = createManagedUrl(blob);
          const fileName = item.path.split("/").pop() || `Página ${idCounter}`;
          newPages.push({
            id: idCounter++,
            name: fileName,
            origBlob: blob,
            origUrl: url,
            transBlob: null,
            transUrl: null,
            status: "idle",
          });
        }
      } else {
        // Múltiples imágenes seleccionadas
        const sortedFiles = Array.from(fileList)
          .filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
          .sort((a, b) => naturalCompare(a.name, b.name));

        setChapterTitle(`Capítulo (${sortedFiles.length} páginas)`);

        let idCounter = 1;
        for (const file of sortedFiles) {
          const url = createManagedUrl(file);
          newPages.push({
            id: idCounter++,
            name: file.name,
            origBlob: file,
            origUrl: url,
            transBlob: null,
            transUrl: null,
            status: "idle",
          });
        }
      }

      if (newPages.length > 0) {
        setPages(newPages);
        setActivePageIndex(0);
      }
    } catch (err) {
      console.error("Error al procesar archivos de capítulo:", err);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  // Traducir una página individual
  const translateSinglePageByIndex = async (index: number): Promise<boolean> => {
    const targetPage = pagesRef.current[index];
    if (!targetPage) return false;

    // Actualizar estado a "translating"
    setPages((prev) =>
      prev.map((p, i) => (i === index ? { ...p, status: "translating", errorMessage: undefined } : p))
    );

    try {
      const formData = new FormData();
      formData.append("file", targetPage.origBlob, targetPage.name);
      formData.append("src_lang", sourceLang);
      formData.append("tgt_lang", targetLang);
      formData.append("model_name", selectedModel);

      const res = await fetch("http://127.0.0.1:8000/translate-single", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || `Error HTTP ${res.status}`);
      }

      const outBlob = await res.blob();
      const outUrl = createManagedUrl(outBlob);

      setPages((prev) =>
        prev.map((p, i) =>
          i === index
            ? {
                ...p,
                transBlob: outBlob,
                transUrl: outUrl,
                status: "done",
                errorMessage: undefined,
              }
            : p
        )
      );
      return true;
    } catch (err: any) {
      console.error(`Error traduciendo página ${index + 1}:`, err);
      setPages((prev) =>
        prev.map((p, i) =>
          i === index
            ? {
                ...p,
                status: "error",
                errorMessage: err.message || "Error al traducir página",
              }
            : p
        )
      );
      return false;
    }
  };

  // Procesar todo el capítulo secuencialmente (Cola de fondo en tiempo real)
  const startTranslateAllQueue = async () => {
    if (isQueueRunningRef.current) return;
    isQueueRunningRef.current = true;
    setIsQueueRunning(true);

    for (let i = 0; i < pagesRef.current.length; i++) {
      if (!isQueueRunningRef.current) break;
      const currentPage = pagesRef.current[i];
      if (currentPage.status === "done") continue;

      // Si el usuario no ha cambiado manualmente de página, opcionalmente centrar
      await translateSinglePageByIndex(i);
    }

    isQueueRunningRef.current = false;
    setIsQueueRunning(false);
  };

  const stopQueue = () => {
    isQueueRunningRef.current = false;
    setIsQueueRunning(false);
  };

  // Atajos de Teclado (Flechas izquierda/derecha para navegar páginas)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (pages.length === 0) return;
      if (e.key === "ArrowLeft") {
        setActivePageIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight") {
        setActivePageIndex((prev) => Math.min(pages.length - 1, prev + 1));
      } else if (e.key === " " && viewMode === "toggle") {
        e.preventDefault();
        setToggleShowOriginal((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pages.length, viewMode]);

  // Asegurar que el thumbnail activo sea visible en el strip horizontal
  useEffect(() => {
    if (thumbnailStripRef.current) {
      const activeEl = thumbnailStripRef.current.children[activePageIndex] as HTMLElement;
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    }
  }, [activePageIndex]);

  // Contadores de progreso del capítulo
  const translatedCount = pages.filter((p) => p.status === "done").length;
  const totalCount = pages.length;
  const progressPercent = totalCount > 0 ? Math.round((translatedCount / totalCount) * 100) : 0;

  const activePage = pages[activePageIndex];

  // Descargar la página actual
  const downloadCurrentPage = () => {
    if (!activePage) return;
    const blobToDownload = activePage.transBlob || activePage.origBlob;
    const url = URL.createObjectURL(blobToDownload);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${activePage.name.replace(/\.[^/.]+$/, "")}_${targetLang.toUpperCase()}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Copiar imagen traducida al portapapeles
  const copyCurrentPage = async () => {
    if (!activePage || !activePage.transBlob) return;
    try {
      const item = new ClipboardItem({ "image/png": activePage.transBlob });
      await navigator.clipboard.write([item]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn("Fallo al copiar imagen al portapapeles:", err);
    }
  };

  // Descargar todo el capítulo empaquetado en ZIP o CBZ con JSZip (Instantáneo en RAM)
  const downloadAllPagesArchive = async () => {
    if (pages.length === 0) return;
    const zip = new JSZip();

    pages.forEach((p, index) => {
      const blob = p.transBlob || p.origBlob;
      const ext = p.transBlob ? "png" : p.name.split(".").pop() || "png";
      const padNum = String(index + 1).padStart(3, "0");
      const baseName = p.name.replace(/\.[^/.]+$/, "");
      const fileName = `${padNum}_${baseName}.${ext}`;
      zip.file(fileName, blob);
    });

    const archiveBlob = await zip.generateAsync({ type: "blob" });
    const ext = outputFormat === "cbz" ? "cbz" : "zip";
    const filename = `${chapterTitle || "Capitulo_Traducido"}_${targetLang.toUpperCase()}.${ext}`;

    const url = URL.createObjectURL(archiveBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Cerrar el capítulo actual y liberar toda la memoria RAM
  const handleCloseChapter = () => {
    stopQueue();
    pages.forEach((p) => {
      revokeManagedUrl(p.origUrl);
      if (p.transUrl) revokeManagedUrl(p.transUrl);
    });
    setPages([]);
    setActivePageIndex(0);
    setChapterTitle("");
    onClearMemoryTrigger();
  };

  // Manejo de Pan y Arrastre en la vista
  const handleMouseDown = (e: React.MouseEvent) => {
    if (scale <= 1) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Pantalla Inicial: Zona de Arrastre para Cargar Archivos
  if (pages.length === 0) {
    return (
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#090b10] relative select-none"
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          multiple
          accept="image/png,image/jpeg,image/webp,.zip,.cbz"
          className="hidden"
        />

        <div className="max-w-xl w-full flex flex-col items-center">
          <div className="relative group cursor-pointer mb-6" onClick={() => fileInputRef.current?.click()}>
            <div className="absolute -inset-2 bg-gradient-to-r from-indigo-500/30 to-purple-500/30 rounded-3xl blur-xl group-hover:opacity-100 opacity-60 transition duration-500" />
            <div className="relative w-28 h-28 rounded-2xl bg-zinc-900/90 border border-indigo-500/30 flex flex-col items-center justify-center shadow-2xl hover:border-indigo-400/60 transition-all">
              {isLoadingFiles ? (
                <Loader2 className="w-12 h-12 text-indigo-400 animate-spin" />
              ) : (
                <UploadCloud className="w-12 h-12 text-indigo-400 group-hover:scale-110 transition-transform" />
              )}
            </div>
          </div>

          <h2 className="text-xl font-bold text-zinc-100 tracking-wide mb-2 flex items-center gap-2">
            Lector y Traductor de Capítulos Manga
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-normal">
              Sin Límites de MB
            </span>
          </h2>

          <p className="text-sm text-zinc-400 mb-6 max-w-md leading-relaxed">
            Arrastra un archivo comprimido <span className="text-indigo-300 font-mono">.ZIP</span>,{" "}
            <span className="text-indigo-300 font-mono">.CBZ</span> o selecciona múltiples páginas de imágenes. Se
            descomprimirán y organizarán instantáneamente en tu memoria RAM.
          </p>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoadingFiles}
            className="flex items-center gap-2.5 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/30 transition-all active:scale-95"
          >
            <FileArchive className="w-4 h-4" />
            {isLoadingFiles ? "Descomprimiendo en RAM..." : "Seleccionar Archivos o ZIP"}
          </button>

          <div className="grid grid-cols-3 gap-4 mt-12 w-full text-left">
            <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
              <Sparkles className="w-4 h-4 text-amber-400 mb-1.5" />
              <div className="text-xs font-semibold text-zinc-200">100% Sin Límites</div>
              <div className="text-[11px] text-zinc-400">Procesa capítulos enteros de 50+ páginas en calidad 4K.</div>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
              <Layers className="w-4 h-4 text-emerald-400 mb-1.5" />
              <div className="text-xs font-semibold text-zinc-200">Navegación Visual</div>
              <div className="text-[11px] text-zinc-400">Lee página por página mientras el resto se traduce.</div>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
              <Download className="w-4 h-4 text-indigo-400 mb-1.5" />
              <div className="text-xs font-semibold text-zinc-200">Exportación Rápida</div>
              <div className="text-[11px] text-zinc-400">Descarga individual o reempaqueta en ZIP/CBZ al instante.</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Interfaz de Trabajo: Lector de Capítulo Completo (Estilo TranslateManga)
  return (
    <div className="flex-1 flex flex-col h-full bg-[#090b10] overflow-hidden select-none">
      {/* Barra de Herramientas del Capítulo */}
      <div className="h-12 bg-zinc-950/90 border-b border-zinc-800/80 px-4 flex items-center justify-between shrink-0">
        {/* Título y Contador de Progreso */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <FileArchive className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-semibold text-zinc-200 truncate max-w-xs">{chapterTitle}</span>
            <span className="text-[11px] text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
              {pages.length} páginas
            </span>
          </div>

          <div className="h-4 w-px bg-zinc-800" />

          {/* Barra de Progreso Dinámica */}
          <div className="flex items-center gap-2.5">
            <div className="w-36 h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-[11px] font-medium text-zinc-300">
              {translatedCount}/{totalCount} ({progressPercent}%)
            </span>
          </div>
        </div>

        {/* Acciones de Traducción y Controles */}
        <div className="flex items-center gap-2">
          {/* Traducir Página Actual */}
          <button
            onClick={() => translateSinglePageByIndex(activePageIndex)}
            disabled={activePage?.status === "translating"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-xs font-medium text-zinc-200 border border-zinc-700/80 transition-all active:scale-95 disabled:opacity-50"
          >
            {activePage?.status === "translating" ? (
              <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            )}
            Traducir esta página
          </button>

          {/* Traducir Todo / Pausar Cola */}
          {isQueueRunning ? (
            <button
              onClick={stopQueue}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium shadow-md transition-all active:scale-95"
            >
              <Pause className="w-3.5 h-3.5" />
              Pausar cola
            </button>
          ) : (
            <button
              onClick={startTranslateAllQueue}
              disabled={translatedCount === totalCount}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-medium shadow-md shadow-indigo-600/30 transition-all active:scale-95 disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              Traducir todo el capítulo
            </button>
          )}

          <div className="h-4 w-px bg-zinc-800" />

          {/* Alternar Modo de Vista (Dividida / Alternar) */}
          <button
            onClick={() => setViewMode((prev) => (prev === "split" ? "toggle" : "split"))}
            title={viewMode === "split" ? "Cambiar a Vista Alternada" : "Cambiar a Vista Dividida"}
            className="p-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition-all"
          >
            {viewMode === "split" ? <Columns className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>

          {/* Descargar Todo (ZIP / CBZ) */}
          <button
            onClick={downloadAllPagesArchive}
            title="Descargar capítulo completo traducido"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-xs font-medium text-emerald-300 border border-emerald-500/30 transition-all active:scale-95"
          >
            <Download className="w-3.5 h-3.5" />
            Descargar ({outputFormat.toUpperCase()})
          </button>

          {/* Cerrar Capítulo */}
          <button
            onClick={handleCloseChapter}
            title="Cerrar capítulo y liberar RAM"
            className="p-1.5 rounded-lg bg-zinc-900 hover:bg-red-950/60 text-zinc-400 hover:text-red-400 border border-zinc-800 hover:border-red-500/30 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Área Principal de Visualización */}
      <div
        className="flex-1 relative flex items-center justify-center overflow-hidden bg-black/40 cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        {/* Controles de Zoom Flotantes */}
        <div className="absolute top-4 right-4 z-30 flex items-center gap-1 bg-zinc-900/90 backdrop-blur-md px-2 py-1 rounded-xl border border-zinc-800 shadow-xl">
          <button
            onClick={() => setScale((s) => Math.max(0.3, s - 0.2))}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-300 transition-all"
            title="Alejar (-)"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="text-xs font-mono text-zinc-300 w-12 text-center">{Math.round(scale * 100)}%</span>
          <button
            onClick={() => setScale((s) => Math.min(4.0, s + 0.2))}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-300 transition-all"
            title="Acercar (+)"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              setScale(1);
              setOffset({ x: 0, y: 0 });
            }}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-300 transition-all"
            title="Restablecer vista (1:1)"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Botones de Navegación Lateral (Anterior / Siguiente) */}
        <button
          onClick={() => setActivePageIndex((prev) => Math.max(0, prev - 1))}
          disabled={activePageIndex === 0}
          className="absolute left-4 z-20 w-11 h-11 rounded-full bg-zinc-900/90 hover:bg-indigo-600 text-zinc-200 hover:text-white border border-zinc-700 flex items-center justify-center shadow-2xl transition-all disabled:opacity-20 disabled:hover:bg-zinc-900"
          title="Página Anterior (←)"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>

        <button
          onClick={() => setActivePageIndex((prev) => Math.min(pages.length - 1, prev + 1))}
          disabled={activePageIndex === pages.length - 1}
          className="absolute right-4 z-20 w-11 h-11 rounded-full bg-zinc-900/90 hover:bg-indigo-600 text-zinc-200 hover:text-white border border-zinc-700 flex items-center justify-center shadow-2xl transition-all disabled:opacity-20 disabled:hover:bg-zinc-900"
          title="Página Siguiente (→)"
        >
          <ChevronRight className="w-6 h-6" />
        </button>

        {/* Lienzo de Imágenes (Dividido o Alternado) */}
        {activePage && (
          <div
            className="flex items-center justify-center w-full h-full p-4 transition-transform duration-75"
            style={{
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            }}
          >
            {viewMode === "split" ? (
              // Vista Dividida (Lado a Lado: Original | Traducido)
              <div className="flex items-center justify-center gap-6 max-h-full max-w-full">
                {/* Panel Original */}
                <div className="flex flex-col items-center">
                  <div className="relative border border-zinc-800 rounded-xl overflow-hidden shadow-2xl bg-zinc-950 flex items-center justify-center max-h-[calc(100vh-210px)]">
                    <img
                      src={activePage.origUrl}
                      alt={`Original - ${activePage.name}`}
                      className="max-h-[calc(100vh-210px)] max-w-[45vw] object-contain pointer-events-none select-none"
                    />
                    <div className="absolute top-2 left-2 px-2.5 py-1 rounded-md bg-black/75 backdrop-blur-md text-[11px] font-semibold text-zinc-200 border border-white/10">
                      Original
                    </div>
                  </div>
                </div>

                {/* Panel Traducido */}
                <div className="flex flex-col items-center">
                  <div className="relative border border-zinc-800 rounded-xl overflow-hidden shadow-2xl bg-zinc-950 flex items-center justify-center max-h-[calc(100vh-210px)] min-w-[280px]">
                    {activePage.status === "translating" ? (
                      <div className="w-[380px] h-[480px] flex flex-col items-center justify-center gap-3 text-center p-6 bg-zinc-950">
                        <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
                        <div className="text-sm font-medium text-zinc-200">Traduciendo con IA...</div>
                        <div className="text-xs text-zinc-400">Limpiando globos y re-tipografiando Scanlation</div>
                      </div>
                    ) : activePage.transUrl ? (
                      <>
                        <img
                          src={activePage.transUrl}
                          alt={`Traducido - ${activePage.name}`}
                          className="max-h-[calc(100vh-210px)] max-w-[45vw] object-contain pointer-events-none select-none"
                        />
                        <div className="absolute top-2 left-2 px-2.5 py-1 rounded-md bg-indigo-950/80 backdrop-blur-md text-[11px] font-semibold text-indigo-200 border border-indigo-400/30 flex items-center gap-1.5">
                          <Sparkles className="w-3 h-3 text-indigo-400" />
                          Traducido ({targetLang.toUpperCase()})
                        </div>
                      </>
                    ) : (
                      <div className="w-[380px] h-[480px] flex flex-col items-center justify-center gap-3 text-center p-6 bg-zinc-950/60">
                        <ImageIcon className="w-10 h-10 text-zinc-600" />
                        <div className="text-xs text-zinc-400">Página pendiente de traducción</div>
                        <button
                          onClick={() => translateSinglePageByIndex(activePageIndex)}
                          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow-md transition-all active:scale-95"
                        >
                          Traducir ahora
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              // Vista Alternar (Pantalla completa con botón para conmutar)
              <div className="relative border border-zinc-800 rounded-xl overflow-hidden shadow-2xl bg-zinc-950 flex items-center justify-center max-h-[calc(100vh-210px)]">
                <img
                  src={
                    toggleShowOriginal || !activePage.transUrl ? activePage.origUrl : activePage.transUrl
                  }
                  alt={activePage.name}
                  className="max-h-[calc(100vh-210px)] max-w-[85vw] object-contain pointer-events-none select-none"
                />

                <div className="absolute top-3 left-3 flex items-center gap-2">
                  <button
                    onClick={() => setToggleShowOriginal((prev) => !prev)}
                    className="px-3 py-1.5 rounded-lg bg-black/80 backdrop-blur-md text-xs font-semibold text-zinc-200 border border-white/20 hover:bg-zinc-800 transition-all flex items-center gap-1.5"
                  >
                    {toggleShowOriginal || !activePage.transUrl ? "Viendo Original" : `Viendo Traducido (${targetLang.toUpperCase()})`}
                    <span className="text-[10px] text-zinc-400">(Barra espaciadora)</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Barra Flotante de Acciones Rápidas para la Página Actual */}
        <div className="absolute bottom-4 z-20 flex items-center gap-2 bg-zinc-900/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-zinc-800 shadow-2xl">
          <span className="text-xs font-medium text-zinc-300 mr-2">
            Página {activePageIndex + 1} de {pages.length}
          </span>

          <button
            onClick={copyCurrentPage}
            disabled={!activePage?.transBlob}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 transition-all disabled:opacity-40"
            title="Copiar imagen traducida al portapapeles"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? "Copiada" : "Copiar"}
          </button>

          <button
            onClick={downloadCurrentPage}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 transition-all"
            title="Descargar imagen actual en PNG"
          >
            <Download className="w-3.5 h-3.5 text-indigo-400" />
            Descargar
          </button>
        </div>
      </div>

      {/* Galería Horizontal de Miniaturas (Filmstrip TranslateManga) */}
      <div className="h-28 bg-zinc-950 border-t border-zinc-800/80 px-4 py-2 shrink-0 flex items-center">
        <div
          ref={thumbnailStripRef}
          className="flex items-center gap-3 overflow-x-auto w-full h-full pb-1 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-900"
        >
          {pages.map((page, index) => {
            const isActive = index === activePageIndex;
            return (
              <div
                key={page.id}
                onClick={() => setActivePageIndex(index)}
                className={`relative shrink-0 h-22 w-16 rounded-lg overflow-hidden cursor-pointer border transition-all duration-150 group ${
                  isActive
                    ? "border-indigo-500 ring-2 ring-indigo-500/40 scale-105"
                    : "border-zinc-800 hover:border-zinc-600 opacity-75 hover:opacity-100"
                }`}
              >
                {/* Imagen Miniatura */}
                <img
                  src={page.transUrl || page.origUrl}
                  alt={page.name}
                  className="w-full h-full object-cover pointer-events-none"
                />

                {/* Número de Página */}
                <div className="absolute top-1 left-1 px-1.5 py-0.2 rounded bg-black/80 text-[10px] font-mono text-zinc-200">
                  {index + 1}
                </div>

                {/* Estado de Traducción */}
                <div className="absolute bottom-1 right-1">
                  {page.status === "translating" ? (
                    <div className="p-0.5 rounded-full bg-zinc-950/80">
                      <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
                    </div>
                  ) : page.status === "done" ? (
                    <div className="p-0.5 rounded-full bg-emerald-950/80">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    </div>
                  ) : page.status === "error" ? (
                    <div className="p-0.5 rounded-full bg-red-950/80">
                      <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
