import { useEffect, useSyncExternalStore } from "react";
import { CheckCircle2, X } from "lucide-react";
import { saveFeedback } from "@/lib/save-feedback";

const VISIBLE_MS = 6000;

export function SaveFeedback(): JSX.Element | null {
  const message = useSyncExternalStore(saveFeedback.subscribe, saveFeedback.snapshot, () => null);
  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => {
      if (saveFeedback.snapshot() === message) saveFeedback.clear();
    }, VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [message]);
  if (!message) return null;
  // Bottom left, so it never sits over the forms in right-hand side panels.
  return <div className="pointer-events-none fixed bottom-4 left-4 z-[70] flex w-[min(24rem,calc(100vw-2rem))] items-start gap-3 rounded-card border border-ok/40 bg-surface p-4 shadow-overlay">
    <CheckCircle2 className="mt-0.5 shrink-0 text-ok" size={20} aria-hidden="true" />
    <p role="status" aria-live="polite" aria-atomic="true" className="min-w-0 flex-1 text-body text-ink">{message}</p>
    <button type="button" className="icon-button pointer-events-auto shrink-0" aria-label="Dismiss saved confirmation" onClick={() => saveFeedback.clear()}><X size={16} aria-hidden="true" /></button>
  </div>;
}
