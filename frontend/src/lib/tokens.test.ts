import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Charts need colour strings rather than class names, so some source files reference token
 * variables directly. A token rename would leave those references resolving to nothing, which
 * renders as black rather than failing loudly. This checks every reference resolves.
 */

const SOURCE_ROOT = join(process.cwd(), "src");
const TOKENS = join(SOURCE_ROOT, "styles", "tokens.css");

function sourceFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) found.push(...sourceFiles(path));
    else if (/\.(tsx?|css)$/.test(entry)) found.push(path);
  }
  return found;
}

function declaredTokens(): Set<string> {
  const css = readFileSync(TOKENS, "utf8");
  return new Set(Array.from(css.matchAll(/^\s*(--[\w-]+)\s*:/gm), (match) => match[1] as string));
}

describe("design tokens", () => {
  it("declares both themes", () => {
    const css = readFileSync(TOKENS, "utf8");
    expect(css).toContain(":root");
    expect(css).toContain('[data-theme="dark"]');
  });

  it("gives every light token a dark counterpart", () => {
    const css = readFileSync(TOKENS, "utf8");
    const darkStart = css.indexOf('[data-theme="dark"]');
    const light = new Set(
      Array.from(css.slice(0, darkStart).matchAll(/^\s*(--[\w-]+)\s*:/gm), (m) => m[1] as string),
    );
    const dark = new Set(
      Array.from(css.slice(darkStart).matchAll(/^\s*(--[\w-]+)\s*:/gm), (m) => m[1] as string),
    );

    // Geometry and motion are intentionally shared across themes.
    const shared = /^--(radius|content|motion|layout|space|font|line)/;
    const missing = [...light].filter((token) => !shared.test(token) && !dark.has(token));
    expect(missing).toEqual([]);
  });

  it("resolves every token referenced in source", () => {
    const declared = declaredTokens();
    const unresolved: string[] = [];

    for (const file of sourceFiles(SOURCE_ROOT)) {
      if (file === TOKENS) continue;
      const contents = readFileSync(file, "utf8");
      for (const match of contents.matchAll(/var\((--[\w-]+)\)/g)) {
        const token = match[1] as string;
        if (!declared.has(token)) {
          unresolved.push(`${file.replace(SOURCE_ROOT, "src")} references ${token}`);
        }
      }
    }

    expect(unresolved).toEqual([]);
  });

  it("keeps raw colors and palette utilities inside the token file", () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SOURCE_ROOT)) {
      if (file === TOKENS || /\.test\./.test(file)) continue;
      const text = readFileSync(file, "utf8");
      if (/#[\da-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(/i.test(text) ||
          /\b(?:bg|text|border|ring)-(?:white|black|(?:slate|gray|blue|red|green|purple|amber|orange)-\d)/.test(text)) {
        offenders.push(file.replace(SOURCE_ROOT, "src"));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("provides non-moving and forced-colour fallbacks for the new action layers", () => {
    const css = readFileSync(join(SOURCE_ROOT, "styles", "godui.css"), "utf8");
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"), css.indexOf("@media (forced-colors: active)"));
    expect(reduced).toMatch(/\.godui-lift-front[^{}]*\.godui-fold-front[^{}]*\{[^}]*transform:\s*none/);
    expect(reduced).toMatch(/\.godui-fold-bar[^{}]*\{[^}]*animation:\s*none/);
    const forced = css.slice(css.indexOf("@media (forced-colors: active)"));
    expect(forced).toMatch(/\.godui-lift-front[^{}]*\.godui-fold-front[^{}]*\{[^}]*ButtonFace[^}]*ButtonText/);
  });

  it("sets tactile button face colors explicitly rather than inheriting preflight text", () => {
    const css = readFileSync(join(SOURCE_ROOT, "styles", "godui.css"), "utf8");
    expect(css).toMatch(/\.godui-lift-front\s*\{[^}]*color:\s*var\(--text-on-accent\)/);
    expect(css).toMatch(/\.godui-lift\[data-variant="secondary"\]\s+\.godui-lift-front\s*\{[^}]*color:\s*var\(--text\)/);
  });

  it("keeps loading animation bounded and disables overlay motion when requested", () => {
    const css = readFileSync(join(SOURCE_ROOT, "styles", "app-chrome.css"), "utf8");
    expect(css).toContain("animation: workspace-skeleton-pass 1.8s ease-in-out 3");
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduced).toMatch(/\.workspace-menu-panel[^{}]*\.workspace-drawer[^{}]*\.workspace-skeleton::after[^{}]*\{[^}]*animation:\s*none/);
  });

  it.each(["light", "dark"])("meets AA text and control contrast in %s theme", (theme) => {
    const css = readFileSync(TOKENS, "utf8");
    const darkStart = css.indexOf('[data-theme="dark"]');
    const block = theme === "light" ? css.slice(0, darkStart) : css.slice(darkStart);
    const colors = Object.fromEntries(Array.from(block.matchAll(/(--[\w-]+):\s*(#[\da-f]{6});/gi), (m) => [m[1]!, m[2]!]));
    const luminance = (hex: string): number => {
      const channels = [1, 3, 5].map((offset) => {
        const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722;
    };
    const contrast = (foreground: string, background: string): number => {
      const a = luminance(colors[foreground]!);
      const b = luminance(colors[background]!);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    };
    for (const text of ["--text", "--text-secondary", "--text-muted"]) {
      for (const background of ["--canvas", "--surface", "--surface-subtle"]) {
        expect(contrast(text, background), `${text} on ${background}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    for (const tone of ["accent", "ok", "warn", "critical", "advisory", "purple", "teal", "cyan", "violet", "indigo"]) {
      expect(contrast(`--${tone}`, `--${tone}-tint`), `${tone} badge`).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast("--text-on-accent", "--accent")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--text-on-accent", "--accent-hover")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--text-on-status", "--critical")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--nav-text", "--nav-surface")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--nav-text-strong", "--nav-active")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--border-strong", "--surface")).toBeGreaterThanOrEqual(3);
  });
});
