import { useEffect, useRef, useCallback } from "react";

/**
 * Hook para la gestión estricta de memoria de Blobs y ObjectURLs en el Frontend.
 * Garantiza el principio de Cero Persistencia revocando de inmediato las URLs
 * asignadas en la memoria del navegador para evitar fugas de memoria (RAM).
 */
export function useMemoryCleanup() {
  const activeUrlsRef = useRef<Set<string>>(new Set());

  // Registra un nuevo Blob y retorna su URL temporal en memoria
  const createManagedUrl = useCallback((blob: Blob): string => {
    const url = URL.createObjectURL(blob);
    activeUrlsRef.current.add(url);
    return url;
  }, []);

  // Revoca una URL individual
  const revokeManagedUrl = useCallback((url: string | null | undefined) => {
    if (!url) return;
    if (activeUrlsRef.current.has(url)) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        console.warn("Error al revocar ObjectURL:", e);
      }
      activeUrlsRef.current.delete(url);
    }
  }, []);

  // Libera todas las URLs de objetos creadas activamente
  const clearAllMemory = useCallback(() => {
    const count = activeUrlsRef.current.size;
    activeUrlsRef.current.forEach((url) => {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        console.warn("Error al revocar ObjectURL durante limpieza total:", e);
      }
    });
    activeUrlsRef.current.clear();
    console.log(`[ClickTranslate] Memoria liberada en navegador: ${count} URLs de objetos revocadas.`);
  }, []);

  // Limpieza automática al desmontar el ciclo de vida
  useEffect(() => {
    return () => {
      clearAllMemory();
    };
  }, [clearAllMemory]);

  return {
    createManagedUrl,
    revokeManagedUrl,
    clearAllMemory,
    activeUrlCount: activeUrlsRef.current.size,
  };
}
