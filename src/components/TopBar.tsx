import React, { useEffect, useState } from "react";
import mascotImg from "../assets/mascot.jpg";
import {
  Zap,
  Layers,
  Globe,
  Cpu,
  Trash2,
  RefreshCw,
  Archive,
  CheckCircle2,
  AlertCircle
} from "lucide-react";

export type AppMode = "quick" | "batch";

export interface TopBarProps {
  currentMode: AppMode;
  onModeChange: (mode: AppMode) => void;
  sourceLang: string;
  onSourceLangChange: (lang: string) => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
  outputFormat: "zip" | "cbz";
  onOutputFormatChange: (fmt: "zip" | "cbz") => void;
  onClearMemory: () => void;
}

const LANGUAGE_OPTIONS = [
  { id: "auto", label: "Automático" },
  { id: "ja", label: "Japonés (Manga)" },
  { id: "ko", label: "Coreano (Manhwa)" },
  { id: "zh", label: "Chino (Manhua)" },
  { id: "en", label: "Inglés" },
];

export const TopBar: React.FC<TopBarProps> = ({
  currentMode,
  onModeChange,
  sourceLang,
  onSourceLangChange,
  selectedModel,
  onModelChange,
  outputFormat,
  onOutputFormatChange,
  onClearMemory,
}) => {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null);

  // Consulta modelos disponibles en Ollama (directo o mediante el backend)
  const fetchOllamaModels = async () => {
    setLoadingModels(true);
    try {
      // Intentar primero con backend FastAPI, luego fallback directo a Ollama
      let models: string[] = [];
      try {
        const resBackend = await fetch("http://127.0.0.1:8000/models");
        if (resBackend.ok) {
          const data = await resBackend.json();
          if (Array.isArray(data.models) && data.models.length > 0) {
            models = data.models;
          }
        }
      } catch (be) {
        // Fallback directo a Ollama localhost:11434
        const resOllama = await fetch("http://localhost:11434/api/tags");
        if (resOllama.ok) {
          const data = await resOllama.json();
          models = (data.models || []).map((m: any) => m.name);
        }
      }

      if (models.length > 0) {
        setAvailableModels(models);
        setOllamaOnline(true);
        if (!selectedModel || !models.includes(selectedModel)) {
          // Seleccionar modelo preferido si está disponible
          const preferred = models.find((m) => m.includes("qwen") || m.includes("gemma")) || models[0];
          onModelChange(preferred);
        }
      } else {
        setOllamaOnline(false);
        // Si no hay respuesta pero el usuario tiene uno configurado
        if (!selectedModel) onModelChange("qwen2.5:7b");
      }
    } catch (err) {
      console.warn("No se pudo conectar a Ollama:", err);
      setOllamaOnline(false);
      if (!selectedModel) onModelChange("qwen2.5:7b");
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    fetchOllamaModels();
  }, []);

  return (
    <header className="h-16 px-4 border-b border-surfaceBorder bg-surface/90 backdrop-blur-md flex items-center justify-between select-none z-30">
      {/* Logotipo y Modos */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="relative group cursor-pointer">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl blur-xs opacity-75 group-hover:opacity-100 transition duration-300" />
            <div className="relative w-9 h-9 rounded-xl overflow-hidden border border-indigo-400/50 bg-zinc-950 flex items-center justify-center">
              <img
                src={mascotImg}
                alt="ClickTranslate Mascot"
                className="w-full h-full object-cover object-center"
              />
            </div>
            <span className="absolute -bottom-1 -right-1 w-3 h-3 bg-emerald-500 border-2 border-zinc-950 rounded-full" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-wide text-zinc-100 flex items-center gap-1.5">
              ClickTranslate
              <span className="text-[10px] font-mono text-indigo-400">「翻訳」</span>
              <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                RAM Mode
              </span>
            </h1>
            <p className="text-[10px] text-zinc-400 leading-none">Manga & Comic AI Translator</p>
          </div>
        </div>

        {/* Pestañas de Modo */}
        <div className="flex items-center bg-zinc-900/90 p-1 rounded-lg border border-surfaceBorder">
          <button
            onClick={() => onModeChange("quick")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all ${
              currentMode === "quick"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>Modo Rápido (Ctrl+V)</span>
          </button>

          <button
            onClick={() => onModeChange("batch")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all ${
              currentMode === "batch"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Lote Capítulo (ZIP / CBZ)</span>
          </button>
        </div>
      </div>

      {/* Controles: Idioma, Modelo Ollama, Formato de Salida y Limpiar Memoria */}
      <div className="flex items-center gap-3">
        {/* Selector de Idioma Origen */}
        <div className="flex items-center gap-1.5 bg-zinc-900/80 px-2.5 py-1.5 rounded-lg border border-surfaceBorder">
          <Globe className="w-3.5 h-3.5 text-zinc-400" />
          <label className="text-[11px] text-zinc-400 font-medium">Origen:</label>
          <select
            value={sourceLang}
            onChange={(e) => onSourceLangChange(e.target.value)}
            className="bg-transparent text-xs text-zinc-200 font-medium focus:outline-none cursor-pointer pr-1"
          >
            {LANGUAGE_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id} className="bg-zinc-900 text-zinc-200">
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Selector de Modelo Ollama */}
        <div className="flex items-center gap-1.5 bg-zinc-900/80 px-2.5 py-1.5 rounded-lg border border-surfaceBorder">
          <Cpu className="w-3.5 h-3.5 text-zinc-400" />
          <label className="text-[11px] text-zinc-400 font-medium">Ollama:</label>
          {availableModels.length > 0 ? (
            <select
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              className="bg-transparent text-xs text-zinc-200 font-medium focus:outline-none cursor-pointer max-w-[130px] truncate"
            >
              {availableModels.map((m) => (
                <option key={m} value={m} className="bg-zinc-900 text-zinc-200">
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              placeholder="qwen2.5:7b"
              className="bg-transparent text-xs text-zinc-200 font-medium w-24 focus:outline-none"
            />
          )}

          <button
            onClick={fetchOllamaModels}
            disabled={loadingModels}
            title={ollamaOnline ? "Ollama conectado" : "Reintentar conexión con Ollama"}
            className="p-0.5 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loadingModels ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Switch Formato de Salida (Solo en modo Lote) */}
        {currentMode === "batch" && (
          <div className="flex items-center bg-zinc-900/80 p-0.5 rounded-lg border border-surfaceBorder">
            <button
              onClick={() => onOutputFormatChange("zip")}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
                outputFormat === "zip"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              .ZIP
            </button>
            <button
              onClick={() => onOutputFormatChange("cbz")}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
                outputFormat === "cbz"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              .CBZ
            </button>
          </div>
        )}

        {/* Botón Limpiar Memoria (Esc) */}
        <button
          onClick={onClearMemory}
          title="Liberar inmediatamente toda la memoria RAM y caché del navegador (Esc)"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 border border-red-500/20 transition-all shadow-sm active:scale-95"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>Limpiar RAM</span>
          <kbd className="px-1 py-0.2 text-[10px] bg-red-900/40 rounded border border-red-500/30 text-red-300">
            Esc
          </kbd>
        </button>
      </div>
    </header>
  );
};
