// Adapted from GodUI's MIT-licensed liquid-glass-card registry item; see LICENSE.txt.
import { forwardRef, useEffect, useId, useRef, useState, type CSSProperties, type HTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { buildDisplacementMap, mergeRefs, RefractionFilter, useRefractionSupport } from "./liquid-glass-utils";

export interface LiquidGlassCardProps extends HTMLAttributes<HTMLDivElement> {
  radius?: number;
  blur?: number;
  strength?: number;
  dispersion?: number;
  saturation?: number;
  tint?: string;
  sheen?: number;
}

export const LiquidGlassCard = forwardRef<HTMLDivElement, LiquidGlassCardProps>(function LiquidGlassCard(
  { children, className, style, radius, blur = 12, strength = 18, dispersion = 0.08, saturation = 1.2, tint,
    sheen = 0.18, onPointerMove, onPointerEnter, onPointerLeave, ...props }, ref,
) {
  const root = useRef<HTMLDivElement>(null);
  const filterId = `lgc-${useId().replace(/:/g, "")}`;
  const [map, setMap] = useState<string | null>(null);
  const [hovering, setHovering] = useState(false);
  const refract = useRefractionSupport();
  useEffect(() => {
    const node = root.current;
    if (!node || !refract || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      const tokens = getComputedStyle(node);
      const colors = ["--godui-map-red", "--godui-map-mid-red", "--godui-map-green", "--godui-map-mid-green", "--godui-map-zero"].map(name => tokens.getPropertyValue(name).trim());
      if (width > 0 && height > 0 && colors.every(Boolean)) setMap(buildDisplacementMap(Math.round(width), Math.round(height), colors));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [refract]);
  const backdrop = `blur(${blur}px) saturate(${saturation})${refract && map ? ` url(#${filterId})` : ""}`;

  return (
    <div ref={mergeRefs(root, ref)} data-slot="liquid-glass-card" className={cn("godui-glass", className)}
      style={{ ...(radius !== undefined ? { borderRadius: `${radius}px` } : {}), ...(tint ? { backgroundColor: tint } : {}), "--godui-glass-sheen": sheen, ...style } as CSSProperties}
      onPointerMove={event => {
        const node = root.current;
        if (node && typeof window.matchMedia === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          const rect = node.getBoundingClientRect();
          if (rect.width && rect.height) {
            node.style.setProperty("--godui-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
            node.style.setProperty("--godui-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
          }
        }
        onPointerMove?.(event);
      }}
      onPointerEnter={event => { setHovering(true); onPointerEnter?.(event); }}
      onPointerLeave={event => { setHovering(false); onPointerLeave?.(event); }} {...props}>
      <div aria-hidden="true" className="godui-glass-frost" style={{ backdropFilter: backdrop, WebkitBackdropFilter: `blur(${blur}px) saturate(${saturation})` }} />
      <div aria-hidden="true" className="godui-glass-sheen" style={{ opacity: hovering ? 1 : 0 }} />
      <div aria-hidden="true" className="godui-glass-rim" />
      {refract && map ? <svg aria-hidden="true" className="absolute h-0 w-0"><RefractionFilter id={filterId} map={map} strength={strength} dispersion={dispersion} /></svg> : null}
      <div className="relative z-10">{children}</div>
    </div>
  );
});