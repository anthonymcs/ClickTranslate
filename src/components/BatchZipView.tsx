import React, { useState, useRef, useEffect } from "react";
import {
  UploadCloud,
  FileArchive,
  Download,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
  FileCheck,
  Sparkles,
  ArrowRight
} from "lucide-react";

interface BatchZipViewProps {
  sourceLang: string;
  targetLang: string;
  selectedModel: string;
  outputFormat: "zip" | "cbz";
  onClearMemoryTrigger: () => void;
}

interface BatchProgress {
  status: "idle" | "uploading" | "processing" | "completed" | "error" | "cancelled";
  page: number;
  total: number;
  percent: number;
  thumbnail: string;
  error?: string;
  filename?: string;
}

export const BatchZipView: React.FC<BatchZipViewProps> = ({
  sourceLang,
  targetLang,
  selectedModel,
  outputFormat,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<BatchProgress>({
    status: "idle",
    page: 0,
    total: 0,
    percent: 0,
    thumbnail: "",
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Cerrar SSE al desmontar
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.name.toLowerCase().endsWith(".zip") || file.name.toLowerCase().endsWith(".cbz")) {
        setSelectedFile(file);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setSelectedFile(file);
    }
  };

  const startBatchTranslation = async () => {
    if (!selectedFile) return;

    setProgress({
      status: "uploading",
      page: 0,
      total: 0,
      percent: 0,
      thumbnail: "",
    });

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("src_lang", sourceLang);
      formData.append("tgt_lang", targetLang);
      formData.append("model_name", selectedModel);
      formData.append("output_format", outputFormat);

      const res = await fetch("http://127.0.0.1:8000/translate-batch", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "Error al subir el archivo para lote");
      }

      const data = await res.json();
      const newJobId = data.job_id;
      setJobId(newJobId);

      // Conectar a Server-Sent Events (SSE)
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`http://127.0.0.1:8000/progress/${newJobId}`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const sseData = JSON.parse(event.data);
          setProgress((prev) => ({
            ...prev,
            status: sseData.status,
            page: sseData.page ?? prev.page,
            total: sseData.total ?? prev.total,
            percent: sseData.percent ?? prev.percent,
            thumbnail: sseData.thumbnail || prev.thumbnail,
            error: sseData.error,
          }));

          if (sseData.status === "completed" || sseData.status === "error") {
            es.close();
          }
        } catch (parseErr) {
          console.error("Error parseando SSE:", parseErr);
        }
      };

      es.onerror = () => {
        console.warn("Conexión SSE cerrada o con error.");
        es.close();
      };
    } catch (err: any) {
      console.error("Error en startBatchTranslation:", err);
      setProgress((prev) => ({
        ...prev,
        status: "error",
        error: err.message || "Error al iniciar lote",
      }));
    }
  };

  const cancelBatch = async () => {
    if (!jobId) return;
    try {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      await fetch(`http://127.0.0.1:8000/cancel/${jobId}`, { method: "POST" });
    } catch (e) {
      console.error("Error al cancelar:", e);
    } finally {
      setProgress((prev) => ({ ...prev, status: "cancelled" }));
    }
  };

  const downloadResult = () => {
    if (!jobId) return;
    const downloadUrl = `http://127.0.0.1:8000/download/${jobId}`;
    const a = document.createElement("a");
    a.href = downloadUrl;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const resetAll = () => {
    if (eventSourceRef.current) eventSourceRef.current.close();
    setSelectedFile(null);
    setJobId(null);
    setProgress({
      status: "idle",
      page: 0,
      total: 0,
      percent: 0,
      thumbnail: "",
    });
  };

  const isProcessing = progress.status === "processing" || progress.status === "uploading";

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] p-6 overflow-y-auto max-w-5xl mx-auto w-full">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
          <FileArchive className="w-5 h-5 text-indigo-400" />
          Traducción por Lote (Capítulo Completo)
        </h2>
        <p className="text-xs text-zinc-400 mt-1">
          Procesa cómics enteros en archivos <span className="font-mono text-zinc-300">.zip</span> o{" "}
          <span className="font-mono text-zinc-300">.cbz</span> página por página en RAM, sin escribir nada en disco.
        </p>
      </div>

      {/* Zona Drag & Drop */}
      {!isProcessing && progress.status !== "completed" && (
        <div
          onDrop={handleFileDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-surfaceBorder hover:border-indigo-500/50 bg-surface/40 hover:bg-surface/70 rounded-2xl p-10 flex flex-col items-center justify-center cursor-pointer transition-all duration-200 group"
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept=".zip,.cbz"
            className="hidden"
          />
          <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 text-indigo-400 group-hover:scale-110 flex items-center justify-center mb-4 transition-transform border border-indigo-500/20">
            <UploadCloud className="w-8 h-8" />
          </div>
          <p className="text-sm font-semibold text-zinc-200 mb-1">
            {selectedFile ? selectedFile.name : "Arrastra tu archivo .ZIP o .CBZ aquí"}
          </p>
          <p className="text-xs text-zinc-500">
            {selectedFile
              ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB seleccionados`
              : "O haz click para explorar tus carpetas"}
          </p>
        </div>
      )}

      {/* Botón Iniciar */}
      {selectedFile && progress.status === "idle" && (
        <div className="mt-4 flex items-center justify-end">
          <button
            onClick={startBatchTranslation}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/20 transition-all active:scale-95"
          >
            <Sparkles className="w-4 h-4" />
            <span>Iniciar Traducción del Capítulo</span>
            <ArrowRight className="w-4 h-4 ml-1" />
          </button>
        </div>
      )}

      {/* Progreso SSE en Vivo y Miniatura */}
      {(isProcessing || progress.status === "completed" || progress.status === "error") && (
        <div className="mt-4 bg-surface rounded-2xl border border-surfaceBorder p-6 flex flex-col gap-6">
          {/* Cabecera del Progreso */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {progress.status === "completed" ? (
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
              ) : progress.status === "error" ? (
                <div className="w-10 h-10 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center border border-rose-500/20">
                  <XCircle className="w-5 h-5" />
                </div>
              ) : (
                <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center border border-indigo-500/20">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
              )}

              <div>
                <h3 className="font-semibold text-sm text-zinc-100">
                  {progress.status === "uploading"
                    ? "Cargando archivo en memoria RAM..."
                    : progress.status === "processing"
                    ? `Traduciendo Página ${progress.page} de ${progress.total || "?"}`
                    : progress.status === "completed"
                    ? "¡Capítulo traducido con éxito!"
                    : "Error en el procesamiento del lote"}
                </h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Formato de salida: <span className="font-mono uppercase text-indigo-400">.{outputFormat}</span>
                </p>
              </div>
            </div>

            <div className="text-right">
              <span className="text-2xl font-bold font-mono text-zinc-100">
                {progress.percent}%
              </span>
            </div>
          </div>

          {/* Barra de Progreso */}
          <div className="w-full bg-zinc-900 rounded-full h-3 overflow-hidden border border-surfaceBorder">
            <div
              className="bg-gradient-to-r from-indigo-500 to-violet-500 h-full rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress.percent}%` }}
            />
          </div>

          {/* Miniatura en Vivo de la Última Página Procesada */}
          {progress.thumbnail && (
            <div className="flex flex-col items-center justify-center py-2">
              <span className="text-[11px] font-medium text-zinc-400 mb-2 uppercase tracking-wider">
                Vista previa en vivo (Página {progress.page})
              </span>
              <div className="relative max-h-72 rounded-xl overflow-hidden border border-surfaceBorder shadow-xl bg-zinc-950">
                <img
                  src={progress.thumbnail}
                  alt={`Página ${progress.page}`}
                  className="max-h-72 object-contain rounded-lg"
                />
              </div>
            </div>
          )}

          {/* Acciones Finales: Descargar o Cancelar */}
          <div className="flex items-center justify-between pt-2 border-t border-surfaceBorder/60">
            {isProcessing ? (
              <button
                onClick={cancelBatch}
                className="px-4 py-2 rounded-lg text-xs font-medium text-rose-400 hover:bg-rose-500/10 border border-rose-500/20 transition-all"
              >
                Cancelar y Liberar RAM
              </button>
            ) : (
              <button
                onClick={resetAll}
                className="px-4 py-2 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-all"
              >
                Traducir otro archivo
              </button>
            )}

            {progress.status === "completed" && (
              <button
                onClick={downloadResult}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm shadow-lg shadow-emerald-600/20 transition-all active:scale-95"
              >
                <Download className="w-4 h-4" />
                <span>Descargar {outputFormat.toUpperCase()} Traducido</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
