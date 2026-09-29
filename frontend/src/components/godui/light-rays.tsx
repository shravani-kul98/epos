// Adapted from GodUI's MIT-licensed light-rays registry item; see LICENSE.txt.
import { forwardRef, useId, type CSSProperties, type HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export interface LightRaysProps extends HTMLAttributes<HTMLDivElement> {
  rayCount?: number;
  color?: string;
  speed?: number;
  angle?: number;
  intensity?: number;
  grain?: number;
  paused?: boolean;
}

export const LightRays = forwardRef<HTMLDivElement, LightRaysProps>(function LightRays(
  { rayCount = 10, color = "var(--accent)", speed = 0.5, angle = -15, intensity = 0.25,
    grain = 0, paused = false, className, style, ...props }, ref,
) {
  const grainId = `light-rays-${useId().replace(/:/g, "")}`;
  const step = 360 / Math.max(1, Math.min(64, rayCount));
  const rayColor = `color-mix(in srgb, ${color}, transparent 55%)`;
  return (
    <div {...props} ref={ref} data-slot="light-rays" data-paused={paused} aria-hidden="true"
      className={cn("godui-light-rays", className)} style={{
        "--godui-rays-speed": `${14 / Math.max(0.05, speed)}s`,
        "--godui-rays-angle": `${angle}deg`,
        "--godui-rays-intensity": intensity,
        ...style,
      } as CSSProperties}>
      <div className="godui-rays-source" style={{ backgroundImage: `radial-gradient(ellipse 60% 40% at 50% -5%, color-mix(in srgb, ${color}, transparent 70%), transparent 70%)` }} />
      <div className="godui-rays-fan" style={{ backgroundImage: `repeating-conic-gradient(from ${angle}deg at 50% 0%, transparent 0deg, ${rayColor} ${step * 0.16}deg, transparent ${step}deg)` }} />
      {grain > 0 ? <svg className="godui-rays-grain" style={{ opacity: grain }} role="presentation">
        <filter id={grainId}><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" /></filter>
        <rect width="100%" height="100%" filter={`url(#${grainId})`} />
      </svg> : null}
    </div>
  );
});