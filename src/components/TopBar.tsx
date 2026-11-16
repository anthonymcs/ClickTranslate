import React, { useEffect, useState } from "react";
import mascotImg from "../assets/mascot.jpg";
import {
  Zap,
  Layers,
  ArrowLeftRight,
  Cpu,
  Trash2,
  RefreshCw,
  Sparkles
} from "lucide-react";

export type AppMode = "quick" | "batch";

export interface TopBarProps {
  currentMode: AppMode;
  onModeChange: (mode: AppMode) => void;
  sourceLang: string;
  onSourceLangChange: (lang: string) => void;
  targetLang: string;
  onTargetLangChange: (lang: string) => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
  outputFormat: "zip" | "cbz";
  onOutputFormatChange: (fmt: "zip" | "cbz") => void;
  onClearMemory: () => void;
}

const SOURCE_LANGUAGES = [
  { id: "auto", label: "✨ Detectar idioma" },
  { id: "en", label: "Inglés" },
  { id: "ja", label: "Japonés (Manga)" },
  { id: "ko", label: "Coreano (Manhwa)" },
  { id: "zh", label: "Chino (Manhua)" },
  { id: "es", label: "Español" },
  { id: "fr", label: "Francés" },
  { id: "de", label: "Alemán" },
  { id: "pt", label: "Portugués" },
  { id: "it", label: "Italiano" },
  { id: "ru", label: "Ruso" },
];

const TARGET_LANGUAGES = [
  { id: "es", label: "Español" },
  { id: "en", label: "Inglés" },
  { id: "ja", label: "Japonés" },
  { id: "pt", label: "Portugués" },
  { id: "fr", label: "Francés" },
  { id: "de", label: "Alemán" },
  { id: "it", label: "Italiano" },
  { id: "ru", label: "Ruso" },
  { id: "ko", label: "Coreano" },
  { id: "zh", label: "Chino" },
];

export const TopBar: React.FC<TopBarProps> = ({
  currentMode,
  onModeChange,
  sourceLang,
  onSourceLangChange,
  targetLang,
  onTargetLangChange,
  selectedModel,
  onModelChange,
  outputFormat,
  onOutputFormatChange,
  onClearMemory,
}) => {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [ollamaOnline, setOllamaOnline] = useState<boolean>(false);

  // Consulta modelos disponibles en Ollama si el usuario tiene Ollama corriendo
  const fetchOllamaModels = async () => {
    setLoadingModels(true);
    try {
      const resBackend = await fetch("http://127.0.0.1:8000/models");
      if (resBackend.ok) {
        const data = await resBackend.json();
        if (Array.isArray(data.models) && data.models.length > 0) {
          setAvailableModels(data.models);
          setOllamaOnline(true);
          return;
        }
      }
      setOllamaOnline(false);
    } catch {
      setOllamaOnline(false);
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    fetchOllamaModels();
  }, []);

  // Intercambiar idiomas (estilo Google Translate)
  const handleSwapLanguages = () => {
    if (sourceLang === "auto") {
      onSourceLangChange(targetLang);
      onTargetLangChange("es" === targetLang ? "en" : "es");
    } else {
      const prevSource = sourceLang;
      onSourceLangChange(targetLang);
      onTargetLangChange(prevSource);
    }
  };

  return (
    <header className="h-16 px-4 border-b border-surfaceBorder bg-surface/90 backdrop-blur-md flex items-center justify-between select-none z-30">
      {/* Logotipo y Selector de Modo */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="relative group cursor-pointer">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl blur-xs opacity-75 group-hover:opacity-100 transition duration-300" />
            <div className="relative w-9 h-9 rounded-xl overflow-hidden border border-indigo-400/50 bg-zinc-950 flex items-center justify-center">
              <img
                src={mascotImg}
                alt="ClickTranslate Mascot"
                className="w-full h-full object-cover object-center"
              />
            </div>
            <span className="absolute -bottom-1 -right-1 w-2.5 h-2.5 bg-emerald-500 border-2 border-zinc-950 rounded-full" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-wide text-zinc-100 flex items-center gap-1.5">
              ClickTranslate
              <span className="text-[10px] font-mono text-indigo-400">「翻訳」</span>
            </h1>
            <p className="text-[10px] text-zinc-400 leading-none">AI Manga & Comic Engine</p>
          </div>
        </div>

        {/* Pestañas de Modo */}
        <div className="flex items-center bg-zinc-900/90 p-1 rounded-lg border border-surfaceBorder ml-2">
          <button
            onClick={() => onModeChange("quick")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
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
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              currentMode === "batch"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Capítulo & Lector (Imágenes / ZIP)</span>
          </button>
        </div>
      </div>

      {/* Esquema de Idiomas estilo Google Translate & Motor */}
      <div className="flex items-center gap-2.5">
        {/* Barra de Idiomas: Origen <-> Destino */}
        <div className="flex items-center bg-zinc-900/90 p-1 rounded-xl border border-surfaceBorder shadow-inner">
          {/* Selector Idioma Origen */}
          <select
            value={sourceLang}
            onChange={(e) => onSourceLangChange(e.target.value)}
            className="bg-transparent text-xs text-zinc-200 font-medium px-2 py-1 focus:outline-none cursor-pointer"
          >
            {SOURCE_LANGUAGES.map((opt) => (
              <option key={opt.id} value={opt.id} className="bg-zinc-900 text-zinc-200">
                {opt.label}
              </option>
            ))}
          </select>

          {/* Botón Intercambiar (<->) */}
          <button
            onClick={handleSwapLanguages}
            title="Intercambiar idiomas"
            className="p-1 mx-1 rounded-md text-zinc-400 hover:text-indigo-300 hover:bg-zinc-800 transition-all active:rotate-180"
          >
            <ArrowLeftRight className="w-3.5 h-3.5" />
          </button>

          {/* Selector Idioma Destino */}
          <select
            value={targetLang}
            onChange={(e) => onTargetLangChange(e.target.value)}
            className="bg-transparent text-xs text-indigo-300 font-semibold px-2 py-1 focus:outline-none cursor-pointer"
          >
            {TARGET_LANGUAGES.map((opt) => (
              <option key={opt.id} value={opt.id} className="bg-zinc-900 text-zinc-200">
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Selector de Modelo de IA (Estilo TranslateManga.net - Sin Tokens) */}
        <div className="flex items-center gap-1.5 bg-zinc-900/90 px-2.5 py-1.5 rounded-xl border border-surfaceBorder">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <label className="text-[11px] text-zinc-400 font-medium">Modelo IA:</label>
          <select
            value={selectedModel}
            onChange={(e) => onModelChange(e.target.value)}
            className="bg-transparent text-xs text-zinc-100 font-semibold focus:outline-none cursor-pointer max-w-[185px] truncate"
          >
            <option value="fast" className="bg-zinc-900 text-zinc-100">
              ⚡ Predeterminado (Ultrarrápido)
            </option>
            <option value="deepseek-ai" className="bg-zinc-900 text-indigo-300">
              ✦ DeepSeek V3 Flash (IA Sin Token)
            </option>
            <option value="gpt-ai" className="bg-zinc-900 text-indigo-300">
              ✦ GPT-4o / OpenAI Fast (IA Sin Token)
            </option>
            <option value="gemini-ai" className="bg-zinc-900 text-indigo-300">
              ✦ Gemini 3 Flash (IA Sin Token)
            </option>
            <option value="claude-ai" className="bg-zinc-900 text-indigo-300">
              ✦ Claude Haiku (IA Sin Token)
            </option>
            {availableModels.map((m) => (
              <option key={m} value={m} className="bg-zinc-900 text-emerald-300">
                🧠 Ollama Local ({m})
              </option>
            ))}
          </select>

          <button
            onClick={fetchOllamaModels}
            disabled={loadingModels}
            title={ollamaOnline ? "Ollama conectado" : "Buscar modelos locales de Ollama"}
            className="p-0.5 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loadingModels ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Switch Formato de Salida (Modo Lote) */}
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
          <span>RAM</span>
          <kbd className="px-1 py-0.2 text-[10px] bg-red-900/40 rounded border border-red-500/30 text-red-300">
            Esc
          </kbd>
        </button>
      </div>
    </header>
  );
};
