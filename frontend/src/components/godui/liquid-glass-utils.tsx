// Adapted from GodUI's MIT-licensed liquid-glass utilities; see LICENSE.txt.
import { useEffect, useState, type MutableRefObject, type Ref, type RefCallback } from "react";

export function buildDisplacementMap(width: number, height: number, colors: readonly string[], band = 0.3): string {
  const lo = (0.5 - band / 2).toFixed(3);
  const hi = (0.5 + band / 2).toFixed(3);
  const [red, midRed, green, midGreen, zero] = colors;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
<linearGradient id="x" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${red}"/><stop offset="${lo}" stop-color="${midRed}"/><stop offset="${hi}" stop-color="${midRed}"/><stop offset="1" stop-color="${zero}"/></linearGradient>
<linearGradient id="y" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${green}"/><stop offset="${lo}" stop-color="${midGreen}"/><stop offset="${hi}" stop-color="${midGreen}"/><stop offset="1" stop-color="${zero}"/></linearGradient>
</defs><rect width="${width}" height="${height}" fill="url(#x)"/><rect width="${width}" height="${height}" fill="url(#y)" style="mix-blend-mode:screen"/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function RefractionFilter({ id, map, strength, dispersion }: { id: string; map: string; strength: number; dispersion: number }): JSX.Element {
  return (
    <filter id={id} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
      <feImage href={map} result="map" preserveAspectRatio="none" />
      <feDisplacementMap in="SourceGraphic" in2="map" scale={strength * (1 + dispersion)} xChannelSelector="R" yChannelSelector="G" result="dispR" />
      <feColorMatrix in="dispR" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="red" />
      <feDisplacementMap in="SourceGraphic" in2="map" scale={strength} xChannelSelector="R" yChannelSelector="G" result="dispG" />
      <feColorMatrix in="dispG" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="green" />
      <feDisplacementMap in="SourceGraphic" in2="map" scale={strength * (1 - dispersion)} xChannelSelector="R" yChannelSelector="G" result="dispB" />
      <feColorMatrix in="dispB" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="blue" />
      <feBlend in="red" in2="green" mode="screen" result="rg" />
      <feBlend in="rg" in2="blue" mode="screen" />
    </filter>
  );
}

export function useRefractionSupport(): boolean {
  const [supported, setSupported] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = (): void => setSupported(!preference.matches && typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("backdrop-filter", "url(#glass)"));
    update();
    preference.addEventListener?.("change", update);
    return () => preference.removeEventListener?.("change", update);
  }, []);
  return supported;
}

export function mergeRefs<T>(...refs: (Ref<T> | undefined)[]): RefCallback<T> {
  return value => {
    for (const ref of refs) {
      if (typeof ref === "function") ref(value);
      else if (ref) (ref as MutableRefObject<T | null>).current = value;
    }
  };
}