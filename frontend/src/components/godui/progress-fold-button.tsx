// Adapted from GodUI's MIT-licensed progress-fold-button registry item; see LICENSE.txt.
import { forwardRef, useEffect, useState, type ButtonHTMLAttributes, type CSSProperties } from "react";
import { cn } from "@/lib/cn";

export interface ProgressFoldButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  size?: "sm" | "md" | "lg";
  status?: "idle" | "loading";
  progress?: number;
  progressLabel?: string;
}

export const ProgressFoldButton = forwardRef<HTMLButtonElement, ProgressFoldButtonProps>(function ProgressFoldButton(
  { variant = "primary", size = "md", status = "idle", progress, progressLabel = "Request in progress",
    children, className, style, type = "button", disabled, ...props }, ref,
) {
  const loading = status === "loading";
  const determinate = loading && progress !== undefined && Number.isFinite(progress);
  const clamped = determinate ? Math.max(0, Math.min(100, progress)) : undefined;
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    setArmed(false);
    if (!loading || !determinate || typeof requestAnimationFrame !== "function") return;
    const frame = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(frame);
  }, [loading, determinate]);

  return <><button {...props} ref={ref} type={type} disabled={disabled || loading}
    data-slot="progress-fold-button" data-variant={variant} data-size={size} data-status={status}
    data-determinate={determinate || undefined} data-armed={armed || undefined} aria-busy={loading || undefined}
    className={cn("godui-fold", className)} style={{ ...style, ...(clamped !== undefined ? { "--godui-fold-fill": clamped / 100 } : {}) } as CSSProperties}>
    <span className="godui-fold-layers" aria-hidden="true"><span className="godui-fold-back" /><span className="godui-fold-bar" /></span>
    <span data-slot="progress-fold-front" className="godui-fold-front">{children}</span>
  </button>
    {loading ? <span className="sr-only" role="progressbar" aria-label={progressLabel} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={clamped} aria-valuetext={clamped === undefined ? "Loading" : `${clamped}%`} /> : null}
  </>;
});
