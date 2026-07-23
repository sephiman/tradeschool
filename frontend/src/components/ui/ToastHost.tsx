import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { dismissToast, subscribeToasts, type Toast } from "@/lib/toastBus";

export function ToastHost() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => subscribeToasts(setToasts), []);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
    >
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => dismissToast(t.id)}
          className={cn(
            "pointer-events-auto flex w-full items-start gap-2 rounded-md px-3 py-2 text-left text-sm font-medium text-white shadow-lg ring-1 ring-black/10",
            t.kind === "success" && "bg-emerald-600 hover:bg-emerald-700",
            t.kind === "error" && "bg-red-600 hover:bg-red-700",
            t.kind === "info" && "bg-gray-700 hover:bg-gray-800",
          )}
        >
          <span className="flex-1">{t.message}</span>
          <span aria-hidden="true" className="opacity-70">×</span>
        </button>
      ))}
    </div>
  );
}
