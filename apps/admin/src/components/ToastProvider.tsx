// Toasts via sonner. Author: Al Amin Ahamed.
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <Toaster />
    </>
  );
}

export interface ToastApi {
  ok: (message: string) => void;
  err: (message: string) => void;
  info: (message: string) => void;
}

export function useToast(): ToastApi {
  return {
    ok: (message) => toast.success(message),
    err: (message) => toast.error(message),
    info: (message) => toast.message(message),
  };
}
