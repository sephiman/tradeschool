export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

type Listener = (toasts: Toast[]) => void;

let counter = 0;
let toasts: Toast[] = [];
const listeners = new Set<Listener>();
const timers = new Map<number, ReturnType<typeof setTimeout>>();

function emit() {
  for (const l of listeners) l(toasts);
}

export function showToast(message: string, kind: ToastKind = "success", durationMs = 3000): number {
  // Identical toast already visible: extend its lifetime instead of stacking a duplicate.
  const existing = toasts.find((t) => t.kind === kind && t.message === message);
  if (existing) {
    const timer = timers.get(existing.id);
    if (timer) clearTimeout(timer);
    if (durationMs > 0) timers.set(existing.id, setTimeout(() => dismissToast(existing.id), durationMs));
    return existing.id;
  }
  const id = ++counter;
  toasts = [...toasts, { id, kind, message }];
  emit();
  if (durationMs > 0) timers.set(id, setTimeout(() => dismissToast(id), durationMs));
  return id;
}

export function dismissToast(id: number) {
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  listener(toasts);
  return () => {
    listeners.delete(listener);
  };
}
