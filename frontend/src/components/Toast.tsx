"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastContextValue {
  push: (kind: ToastKind, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, kind, message }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-md">
        {items.map((t) => (
          <ToastView key={t.id} item={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  const color =
    item.kind === "success"
      ? "border-emerald-600 bg-emerald-950/80 text-emerald-100"
      : item.kind === "error"
        ? "border-red-700 bg-red-950/80 text-red-100"
        : "border-slate-700 bg-slate-900/80 text-slate-100";

  const icon =
    item.kind === "success" ? "✓" : item.kind === "error" ? "✕" : "ℹ";

  return (
    <div
      className={`flex items-start gap-3 rounded border px-4 py-3 shadow-lg ${color}`}
    >
      <span className="text-lg leading-none">{icon}</span>
      <div className="flex-1 text-sm whitespace-pre-wrap break-words">
        {item.message}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-current opacity-70 hover:opacity-100"
        aria-label="닫기"
      >
        ✕
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}
