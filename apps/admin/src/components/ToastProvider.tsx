// Toast notifications (context + container). Author: Al Amin Ahamed.
import { CheckCircle2, Info, XCircle } from "lucide-react";
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";

type ToastTone = "ok" | "err" | "info";
interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastApi {
  ok: (message: string) => void;
  err: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const ICONS = { ok: CheckCircle2, err: XCircle, info: Info };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((tone: ToastTone, message: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, tone, message }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4000);
  }, []);

  const api: ToastApi = {
    ok: (m) => push("ok", m),
    err: (m) => push("err", m),
    info: (m) => push("info", m),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone];
          return (
            <div
              key={t.id}
              className={cn(
                "flex min-w-[240px] max-w-sm items-center gap-2.5 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-sm shadow-lg",
                t.tone === "ok" && "border-l-4 border-l-ok",
                t.tone === "err" && "border-l-4 border-l-err",
                t.tone === "info" && "border-l-4 border-l-accent",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  t.tone === "ok" && "text-ok",
                  t.tone === "err" && "text-err",
                  t.tone === "info" && "text-accent",
                )}
              />
              <span>{t.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
