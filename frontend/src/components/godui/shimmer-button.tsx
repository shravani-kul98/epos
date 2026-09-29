// Adapted from GodUI's MIT-licensed shimmer-button registry item; see LICENSE.txt.
import { forwardRef, useRef, useState, type ButtonHTMLAttributes, type CSSProperties } from "react";
import { cn } from "@/lib/cn";

export interface ShimmerButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  shimmer?: boolean;
  contentClassName?: string;
  shimmerColor?: string;
  shimmerSize?: string;
  shimmerDuration?: string;
  borderRadius?: string;
  background?: string;
}

export const ShimmerButton = forwardRef<HTMLButtonElement, ShimmerButtonProps>(function ShimmerButton(
  {
    variant = "primary", size = "md", shimmer = true, shimmerColor,
    shimmerSize = "1px", shimmerDuration = "var(--motion-shimmer)", borderRadius,
    background, className, contentClassName, style, children, type = "button",
    onMouseEnter, onMouseLeave, onFocus, onBlur, onKeyDown, onKeyUp, ...props
  }, ref,
) {
  const spark = useRef<HTMLSpanElement>(null);
  const [pressed, setPressed] = useState(false);
  function setSparkRate(rate: number): void {
    spark.current?.getAnimations?.({ subtree: true }).forEach(animation => { animation.playbackRate = rate; });
  }
  return (
    <button
      ref={ref} type={type} data-slot="shimmer-button" data-variant={variant} data-size={size}
      data-shimmer={shimmer || undefined} data-pressed={pressed || undefined}
      className={cn("godui-shimmer", className)}
      style={{
        "--godui-shimmer-speed": shimmerDuration,
        "--godui-shimmer-cut": shimmerSize,
        ...(shimmerColor ? { "--godui-shimmer-color": shimmerColor } : {}),
        ...(borderRadius ? { borderRadius } : {}),
        ...(background ? { "--godui-button-bg": background } : {}),
        ...style,
      } as CSSProperties}
      onMouseEnter={event => { setSparkRate(3); onMouseEnter?.(event); }}
      onMouseLeave={event => { setSparkRate(1); setPressed(false); onMouseLeave?.(event); }}
      onFocus={event => { if (event.target.matches(":focus-visible")) setSparkRate(3); onFocus?.(event); }}
      onBlur={event => { setSparkRate(1); setPressed(false); onBlur?.(event); }}
      onKeyDown={event => { if (event.key === "Enter" || event.key === " ") setPressed(true); onKeyDown?.(event); }}
      onKeyUp={event => { if (event.key === "Enter" || event.key === " ") setPressed(false); onKeyUp?.(event); }}
      {...props}
    >
      <span ref={spark} className="godui-shimmer-track" aria-hidden="true">
        <span className="godui-shimmer-slide"><span className="godui-shimmer-spark" /></span>
      </span>
      <span className="godui-shimmer-cut" aria-hidden="true" />
      <span className={cn("godui-shimmer-label", contentClassName)}>{children}</span>
    </button>
  );
});