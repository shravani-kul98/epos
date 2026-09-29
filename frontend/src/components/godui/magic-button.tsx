// Adapted from GodUI's MIT-licensed magic-button registry item; see LICENSE.txt.
import { forwardRef, useCallback, useEffect, useRef, useState, type ButtonHTMLAttributes, type MutableRefObject } from "react";
import { cn } from "@/lib/cn";

export interface MagicButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  size?: "sm" | "md" | "lg";
  rainbow?: boolean;
}

export const MagicButton = forwardRef<HTMLButtonElement, MagicButtonProps>(function MagicButton(
  { variant = "primary", size = "md", rainbow = false, children, className, type = "button",
    onKeyDown, onKeyUp, onBlur, disabled, ...props }, ref,
) {
  const [pressed, setPressed] = useState(false);
  const root = useRef<HTMLButtonElement | null>(null);
  const setRefs = useCallback((node: HTMLButtonElement | null) => {
    root.current = node;
    if (typeof ref === "function") ref(node);
    else if (ref) (ref as MutableRefObject<HTMLButtonElement | null>).current = node;
  }, [ref]);

  useEffect(() => {
    if (!rainbow || !root.current || typeof IntersectionObserver === "undefined") return;
    const node = root.current;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry) node.style.setProperty("--godui-lift-play-state", entry.isIntersecting ? "running" : "paused");
    }, { rootMargin: "128px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [rainbow]);

  return <button {...props} ref={setRefs} type={type} disabled={disabled}
    data-slot="magic-button" data-variant={variant} data-size={size} data-rainbow={rainbow || undefined}
    data-pressed={pressed && !disabled || undefined} className={cn("godui-lift", className)}
    onKeyDown={event => { onKeyDown?.(event); if (!event.defaultPrevented && (event.key === "Enter" || event.key === " ")) setPressed(true); }}
    onKeyUp={event => { if (event.key === "Enter" || event.key === " ") setPressed(false); onKeyUp?.(event); }}
    onBlur={event => { setPressed(false); onBlur?.(event); }}>
    <span className="godui-lift-shadow" aria-hidden="true" />
    <span className="godui-lift-edge" aria-hidden="true" />
    <span className="godui-lift-front">{children}</span>
  </button>;
});
