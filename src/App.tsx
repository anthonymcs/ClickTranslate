import React, { useState, useEffect, useCallback } from "react";
import { TopBar, AppMode } from "./components/TopBar";
import { ClipboardView } from "./components/ClipboardView";
import { BatchZipView } from "./components/BatchZipView";
import { SplashScreen } from "./components/SplashScreen";
import { useMemoryCleanup } from "./hooks/useMemoryCleanup";
import { CheckCircle2 } from "lucide-react";

export function App() {
  const [isLoaded, setIsLoaded] = useState(false);
  const [currentMode, setCurrentMode] = useState<AppMode>("quick");
  const [sourceLang, setSourceLang] = useState<string>("auto");
  const [targetLang, setTargetLang] = useState<string>("es");
  const [selectedModel, setSelectedModel] = useState<string>("fast");
  const [outputFormat, setOutputFormat] = useState<"zip" | "cbz">("zip");
  const [showCleanToast, setShowCleanToast] = useState(false);

  const { createManagedUrl, revokeManagedUrl, clearAllMemory } = useMemoryCleanup();

  // Acción de limpieza global
  const handleClearMemory = useCallback(() => {
    clearAllMemory();
    setShowCleanToast(true);
    setTimeout(() => setShowCleanToast(false), 2200);
  }, [clearAllMemory]);

  // Atajo de teclado global: tecla Escape para liberar memoria de inmediato
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleClearMemory();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleClearMemory]);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#090b10] text-zinc-100 select-none overflow-hidden font-sans">
      {/* Pantalla de Carga Anime / Splash Screen */}
      {!isLoaded && <SplashScreen onLoaded={() => setIsLoaded(true)} />}

      {/* Barra de Control Superior */}
      <TopBar
        currentMode={currentMode}
        onModeChange={setCurrentMode}
        sourceLang={sourceLang}
        onSourceLangChange={setSourceLang}
        targetLang={targetLang}
        onTargetLangChange={setTargetLang}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        outputFormat={outputFormat}
        onOutputFormatChange={setOutputFormat}
        onClearMemory={handleClearMemory}
      />

      {/* Contenido Principal según el Modo */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        {currentMode === "quick" ? (
          <ClipboardView
            sourceLang={sourceLang}
            targetLang={targetLang}
            selectedModel={selectedModel}
            createManagedUrl={createManagedUrl}
            revokeManagedUrl={revokeManagedUrl}
            onClearMemoryTrigger={handleClearMemory}
          />
        ) : (
          <BatchZipView
            sourceLang={sourceLang}
            targetLang={targetLang}
            selectedModel={selectedModel}
            outputFormat={outputFormat}
            onClearMemoryTrigger={handleClearMemory}
          />
        )}
      </main>

      {/* Notificación Toast al pulsar Esc o Limpiar RAM */}
      {showCleanToast && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-zinc-900 border border-zinc-700/80 shadow-2xl shadow-black/80 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-medium text-zinc-200">
            Memoria RAM y ObjectURLs liberados inmediatamente
          </span>
        </div>
      )}
    </div>
  );
}

export default App;
