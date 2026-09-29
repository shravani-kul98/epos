// Adapted from GodUI's MIT-licensed spotlight-card registry item; see LICENSE.txt.
import { createElement, forwardRef, useImperativeHandle, useRef, type CSSProperties, type HTMLAttributes, type PointerEvent } from "react";
import { cn } from "@/lib/cn";

export interface SpotlightCardProps extends HTMLAttributes<HTMLElement> {
  as?: "div" | "section";
  contain?: boolean;
  wrapContent?: boolean;
  glowColor?: string;
  radius?: number;
  border?: boolean;
}

export const SpotlightCard = forwardRef<HTMLElement, SpotlightCardProps>(function SpotlightCard(
  { as = "div", contain = true, wrapContent = true, glowColor = "var(--godui-glow)", radius = 350, border = true, className, style, children, onPointerMove, ...props }, forwardedRef,
) {
  const root = useRef<HTMLElement>(null);
  useImperativeHandle(forwardedRef, () => root.current as HTMLElement);
  return createElement(as, {
      ...props, ref: root, "data-slot": "spotlight-card", "data-contain": contain,
      className: cn("godui-spotlight", className),
      style: { "--godui-spot-color": glowColor, "--godui-spot-radius": `${radius}px`, ...style } as CSSProperties,
      onPointerMove: (event: PointerEvent<HTMLElement>) => {
        const node = root.current;
        if (node && typeof window.matchMedia === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          const rect = node.getBoundingClientRect();
          node.style.setProperty("--godui-x", `${event.clientX - rect.left}px`);
          node.style.setProperty("--godui-y", `${event.clientY - rect.top}px`);
        }
        onPointerMove?.(event);
      },
    }, <>
      <div aria-hidden="true" className="godui-spotlight-glow" />
      {border ? <div aria-hidden="true" className="godui-spotlight-border" /> : null}
      {wrapContent ? <div className="relative z-10">{children}</div> : children}
    </>
  );
});