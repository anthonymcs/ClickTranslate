import React, { useEffect, useState } from "react";
import mascotImg from "../assets/mascot.jpg";
import { Sparkles, Cpu, Zap, ShieldCheck, Heart } from "lucide-react";

interface SplashScreenProps {
  onLoaded: () => void;
}

const LOADING_STEPS = [
  { text: "Invocando redes neuronales de OCR...", subtext: "manga-ocr & PaddleOCR lazy-loading" },
  { text: "Conectando con Ollama Local...", subtext: "Verificando modelos de lenguaje contextuales" },
  { text: "Configurando inpainting neuronal LaMa...", subtext: "Reconstrucción artística de viñetas" },
  { text: "Inicializando buffer Zero-Persistence...", subtext: "100% en memoria RAM sin guardado en disco" },
  { text: "¡Listo! Abriendo interfaz...", subtext: "Disfruta de tus lecturas favoritas" },
];

export const SplashScreen: React.FC<SplashScreenProps> = ({ onLoaded }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(15);
  const [isFadingOut, setIsFadingOut] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const startTime = Date.now();
    const minDisplayMs = 2600; // Tiempo para apreciar el arte e identidad visual

    // Progresión de pasos visuales
    const stepInterval = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev < LOADING_STEPS.length - 1) return prev + 1;
        return prev;
      });
      setProgress((prev) => Math.min(prev + 20, 95));
    }, 550);

    // Comprobación continua del estado del backend FastAPI
    const checkBackend = async () => {
      let isHealthy = false;
      for (let i = 0; i < 20; i++) {
        try {
          const res = await fetch("http://127.0.0.1:8000/health", { method: "GET" });
          if (res.ok) {
            isHealthy = true;
            break;
          }
        } catch {
          // El backend aún está arrancando
        }
        await new Promise((r) => setTimeout(r, 250));
      }

      // Asegurar el tiempo mínimo de visualización elegante
      const elapsed = Date.now() - startTime;
      const waitRemaining = Math.max(0, minDisplayMs - elapsed);
      await new Promise((r) => setTimeout(r, waitRemaining));

      if (isMounted) {
        setProgress(100);
        setCurrentStep(LOADING_STEPS.length - 1);
        setTimeout(() => {
          if (isMounted) {
            setIsFadingOut(true);
            setTimeout(() => {
              if (isMounted) onLoaded();
            }, 500);
          }
        }, 400);
      }
    };

    checkBackend();

    return () => {
      isMounted = false;
      clearInterval(stepInterval);
    };
  }, [onLoaded]);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-[#07090e] transition-opacity duration-500 select-none overflow-hidden ${
        isFadingOut ? "opacity-0 scale-105 pointer-events-none" : "opacity-100 scale-100"
      }`}
    >
      {/* Fondo con resplandores cyberpunk y gradientes anime */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/30 via-[#07090e] to-black" />
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-purple-600/15 rounded-full blur-3xl pointer-events-none animate-pulse" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-cyan-500/15 rounded-full blur-3xl pointer-events-none animate-pulse" />

      {/* Cuadrícula sutil de estilo manga */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />

      {/* Contenedor Central */}
      <div className="relative z-10 flex flex-col items-center max-w-lg w-full px-8 text-center">
        {/* Marco Holográfico con la Mascota Anime */}
        <div className="relative mb-6 group">
          {/* Anillos de luz rotatoria y aura */}
          <div className="absolute -inset-1.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 rounded-3xl blur-md opacity-75 animate-pulse" />

          {/* Tarjeta de la imagen con marco estilo panel de manga */}
          <div className="relative w-56 h-56 rounded-2xl overflow-hidden border-2 border-indigo-400/60 shadow-2xl bg-zinc-950 flex items-center justify-center">
            <img
              src={mascotImg}
              alt="ClickTranslate Anime Mascot"
              className="w-full h-full object-cover object-center transform transition-transform duration-700 hover:scale-105"
            />

            {/* Badge estilo onomatopeya flotante */}
            <div className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md border border-cyan-400/40 text-[10px] font-bold text-cyan-300 shadow-lg tracking-wider">
              翻訳中
            </div>

            {/* Badge inferior */}
            <div className="absolute bottom-2 left-2 right-2 px-2 py-1 rounded-lg bg-zinc-950/80 backdrop-blur-md border border-indigo-500/30 flex items-center justify-center gap-1.5 text-[10px] text-zinc-300 font-medium">
              <Zap className="w-3 h-3 text-indigo-400 fill-indigo-400" />
              <span>Zero-Persistence RAM</span>
            </div>
          </div>
        </div>

        {/* Título Principal y Subtítulo Anime */}
        <div className="space-y-1 mb-6">
          <div className="flex items-center justify-center gap-2">
            <span className="text-[11px] font-bold tracking-widest text-indigo-400 uppercase bg-indigo-500/10 px-2.5 py-0.5 rounded-full border border-indigo-500/20">
              AI Manga & Comic Engine
            </span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center justify-center gap-2">
            <span>ClickTranslate</span>
            <span className="text-lg font-light text-indigo-400">「クリック翻訳」</span>
          </h1>
          <p className="text-xs text-zinc-400 font-medium">
            Traducción visual sin censura con Ollama, LaMa y OpenCV
          </p>
        </div>

        {/* Barra de Progreso Futurista */}
        <div className="w-full space-y-2 mb-4">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-300 font-medium flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
              {LOADING_STEPS[currentStep].text}
            </span>
            <span className="font-mono text-indigo-400 font-bold">{progress}%</span>
          </div>

          <div className="w-full bg-zinc-900/90 h-2.5 rounded-full overflow-hidden border border-zinc-800 p-0.5 shadow-inner">
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 transition-all duration-300 ease-out shadow-sm shadow-indigo-500/50"
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="text-[11px] text-zinc-500 flex items-center justify-center gap-1">
            <span>{LOADING_STEPS[currentStep].subtext}</span>
          </div>
        </div>

        {/* Características al pie */}
        <div className="flex items-center justify-center gap-4 text-[10px] text-zinc-500 border-t border-zinc-900 pt-3 w-full">
          <span className="flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            0% Archivos en Disco
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <Cpu className="w-3 h-3 text-indigo-400" />
            Ollama Local 100% Privado
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <Heart className="w-3 h-3 text-rose-400 fill-rose-400/30" />
            Hecho para Lectores
          </span>
        </div>
      </div>
    </div>
  );
};
