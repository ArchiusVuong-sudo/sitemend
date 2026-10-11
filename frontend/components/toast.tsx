"use client";

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { cx, Icon } from "./ui";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  title: string;
  body?: string;
}

const ToastContext = createContext<(t: Omit<Toast, "id">) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all.slice(-1), { ...t, id }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), t.tone === "error" ? 9000 : 5000);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-96 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto flex gap-3 rounded-xl border bg-white px-4 py-3 shadow-lg",
              t.tone === "error" ? "border-rose-200" : "border-slate-200",
            )}
          >
            <span
              className={cx(
                "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full",
                t.tone === "success" && "bg-emerald-100 text-emerald-700",
                t.tone === "error" && "bg-rose-100 text-rose-700",
                t.tone === "info" && "bg-slate-100 text-slate-700",
              )}
            >
              <Icon name={t.tone === "error" ? "x" : "check"} className="size-3" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-900">{t.title}</p>
              {t.body && <p className="mt-0.5 text-[13px] leading-snug text-slate-500">{t.body}</p>}
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
