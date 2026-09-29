// Adapted from GodUI's MIT-licensed blueprint-grid registry item; see LICENSE.txt.
import { forwardRef, useEffect, useImperativeHandle, useRef, type CSSProperties, type HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export interface BlueprintGridProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "lines" | "dots" | "perspective";
  cellSize?: number;
  color?: string;
  sweep?: boolean;
  sweepDuration?: number;
  spotlight?: boolean;
  spotlightColor?: string;
  spotlightRadius?: number;
}

export const BlueprintGrid = forwardRef<HTMLDivElement, BlueprintGridProps>(function BlueprintGrid(
  { variant = "lines", cellSize = 48, color = "var(--godui-grid)", sweep = true, sweepDuration = 18,
    spotlight = true, spotlightColor = "var(--godui-primary)", spotlightRadius = 220, className, style, ...props }, ref,
) {
  const root = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => root.current as HTMLDivElement);
  useEffect(() => {
    const node = root.current;
    if (!node || !spotlight) return;
    const target = node.offsetParent ?? node.parentElement ?? node;
    const onMove = (event: Event): void => {
      if (typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const pointer = event as PointerEvent;
      const rect = node.getBoundingClientRect();
      node.style.setProperty("--godui-x", `${pointer.clientX - rect.left}px`);
      node.style.setProperty("--godui-y", `${pointer.clientY - rect.top}px`);
      node.style.setProperty("--godui-grid-opacity", "0.55");
    };
    const onLeave = (): void => node.style.setProperty("--godui-grid-opacity", "0");
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerleave", onLeave);
    return () => { target.removeEventListener("pointermove", onMove); target.removeEventListener("pointerleave", onLeave); };
  }, [spotlight]);
  const buildGrid = (ink: string): string => variant === "dots"
    ? `radial-gradient(${ink} 1px, transparent 1.5px)`
    : `linear-gradient(to right, ${ink} 1px, transparent 1px), linear-gradient(to bottom, ${ink} 1px, transparent 1px)`;
  const backgroundSize = variant === "dots" ? `${cellSize}px ${cellSize}px` : `${cellSize}px ${cellSize}px, ${cellSize}px ${cellSize}px`;
  const spotMask = `radial-gradient(circle ${spotlightRadius}px at var(--godui-x) var(--godui-y), var(--godui-mask) 35%, transparent 75%)`;
  return (
    <div ref={root} data-slot="blueprint-grid" aria-hidden="true" className={cn("godui-blueprint", className)} style={style} {...props}>
      <div className={cn("godui-blueprint-grid", variant === "perspective" && "godui-blueprint-perspective")} style={{ backgroundImage: buildGrid(color), backgroundSize }} />
      {spotlight && variant !== "perspective" ? <div className="godui-blueprint-spot" style={{ backgroundImage: buildGrid(spotlightColor), backgroundSize, maskImage: spotMask, WebkitMaskImage: spotMask }} /> : null}
      {sweep ? <div className="godui-blueprint-sweep" style={{ "--godui-sweep-speed": `${sweepDuration}s` } as CSSProperties} /> : null}
    </div>
  );
});