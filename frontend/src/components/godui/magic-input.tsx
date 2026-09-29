// Adapted from GodUI's MIT-licensed magic-input registry item; see LICENSE.txt.
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties, type InputHTMLAttributes, type ReactNode } from "react";
import { ArrowRight, Check, LoaderCircle, X } from "lucide-react";
import { cn } from "@/lib/cn";

export interface MagicInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "onSubmit"> {
  variant?: "primary" | "secondary";
  size?: "sm" | "md" | "lg";
  depth?: "focus" | "always";
  rainbow?: boolean;
  submitButton?: boolean;
  onSubmit?: (value: string) => void;
  submitLabel?: string;
  status?: "idle" | "loading" | "success" | "error";
  progress?: number;
  leadingIcon?: ReactNode;
  inputClassName?: string;
  inputStyle?: CSSProperties;
  nativeSize?: number;
  nativeOnSubmit?: InputHTMLAttributes<HTMLInputElement>["onSubmit"];
}

const RING_RADIUS = 9;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

export const MagicInput = forwardRef<HTMLInputElement, MagicInputProps>(function MagicInput(
  {
    className, inputClassName, inputStyle, style, variant = "primary", size = "md", depth = "focus",
    rainbow = true, submitButton = false, onSubmit, submitLabel = "Submit", status = "idle",
    progress, onKeyDown, disabled, readOnly, leadingIcon, nativeSize, nativeOnSubmit, ...props
  }, ref,
) {
  const input = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => input.current as HTMLInputElement);
  const [armed, setArmed] = useState(false);
  const isLoading = status === "loading";
  const showButton = submitButton || onSubmit !== undefined;
  const clamped = progress === undefined ? undefined : Math.max(0, Math.min(100, progress));
  useEffect(() => {
    setArmed(false);
    if (!isLoading) return;
    const frame = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(frame);
  }, [isLoading]);

  return (
    <div
      data-slot="magic-input" data-variant={variant} data-size={size} data-depth={depth}
      data-status={status} data-rainbow={rainbow || undefined} data-submit={showButton || undefined}
      data-leading={Boolean(leadingIcon) || undefined} data-disabled={disabled || undefined}
      data-determinate={isLoading && clamped !== undefined || undefined} data-armed={armed || undefined}
      className={cn("godui-input", className)}
      style={{ ...(clamped !== undefined ? { "--godui-input-progress": `${clamped}%` } : {}), ...style } as CSSProperties}
    >
      <span className="godui-input-shadow" aria-hidden="true" />
      <span className="godui-input-edge" aria-hidden="true" />
      <input
        ref={input} size={nativeSize} onSubmit={nativeOnSubmit} style={inputStyle} className={cn("control godui-input-front", inputClassName)} disabled={disabled}
        readOnly={readOnly || isLoading || status === "success"} aria-busy={isLoading || undefined}
        onKeyDown={event => {
          onKeyDown?.(event);
          if (status === "idle" && onSubmit && event.key === "Enter" && !event.defaultPrevented) {
            event.preventDefault();
            onSubmit(event.currentTarget.value);
          }
        }}
        {...props}
      />
      {leadingIcon ? <span aria-hidden="true" className="godui-input-icon">{leadingIcon}</span> : null}
      {status !== "idle" ? (
        <span className="sr-only" role="progressbar" aria-label={submitLabel} aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={isLoading ? clamped : undefined}
          aria-valuetext={status === "success" ? "Success" : status === "error" ? "Error" : clamped === undefined ? "Loading" : `${clamped}%`} />
      ) : null}
      {showButton ? (
        <button type={onSubmit ? "button" : "submit"} className="godui-input-submit"
          aria-label={submitLabel} disabled={disabled || status !== "idle"}
          onClick={onSubmit ? () => onSubmit(input.current?.value ?? "") : undefined}>
          <span className="godui-input-state" data-active={status === "idle"} aria-hidden="true"><ArrowRight size={18} /></span>
          <span className="godui-input-state" data-active={isLoading} aria-hidden="true">
            {clamped === undefined ? <LoaderCircle className="godui-spinner" size={18} /> : (
              <svg viewBox="0 0 24 24" width="18" height="18">
                <circle cx="12" cy="12" r={RING_RADIUS} fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2.5" />
                <circle cx="12" cy="12" r={RING_RADIUS} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                  strokeDasharray={RING_LENGTH} strokeDashoffset={RING_LENGTH * (1 - clamped / 100)} transform="rotate(-90 12 12)" />
              </svg>
            )}
          </span>
          <span className="godui-input-state" data-active={status === "success"} aria-hidden="true"><Check size={18} /></span>
          <span className="godui-input-state" data-active={status === "error"} aria-hidden="true"><X size={18} /></span>
        </button>
      ) : null}
    </div>
  );
});