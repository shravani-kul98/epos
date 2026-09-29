import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShimmerButton } from "./shimmer-button";
import { LiquidGlassCard } from "./liquid-glass-card";
import { SpotlightCard } from "./spotlight-card";
import { Card } from "@/components/ui/card";

describe("GodUI compatibility", () => {
  it("keeps native button semantics and composes event handlers without Web Animations", () => {
    const click = vi.fn(); const hover = vi.fn();
    render(<ShimmerButton type="submit" onClick={click} onMouseEnter={hover}>Continue</ShimmerButton>);
    const button = screen.getByRole("button", { name: "Continue" });
    expect(button).toHaveAttribute("type", "submit");
    fireEvent.mouseEnter(button);
    fireEvent.click(button);
    expect(hover).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
  });
  it("does not activate a disabled shimmer button", () => {
    const click = vi.fn();
    render(<ShimmerButton disabled onClick={click}>Waiting</ShimmerButton>);
    fireEvent.click(screen.getByRole("button", { name: "Waiting" }));
    expect(click).not.toHaveBeenCalled();
  });
  it("keeps a readable glass fallback without SVG refraction support", () => {
    render(<LiquidGlassCard><h2>Readable content</h2></LiquidGlassCard>);
    expect(screen.getByRole("heading", { name: "Readable content" })).toBeVisible();
  });
  it("preserves semantic card regions and direct content", () => {
    const { container } = render(<Card aria-label="Evidence" id="evidence"><header>Records</header><div>Details</div></Card>);
    expect(screen.getByRole("region", { name: "Evidence" }).tagName).toBe("SECTION");
    expect(container.querySelector("section > header")).toHaveTextContent("Records");
  });
  it("does not force content wrappers to fill a cyclic percentage height", () => {
    render(<SpotlightCard><h2>Content-sized panel</h2></SpotlightCard>);
    expect(screen.getByRole("heading", { name: "Content-sized panel" }).parentElement).not.toHaveClass("h-full");
  });
  it("retains registry attribution, semantic mappings and reduced-motion CSS", () => {
    const root = process.cwd();
    const registry = JSON.parse(readFileSync(join(root, "components.json"), "utf8"));
    expect(registry.registries["@godui"]).toBe("https://godui.design/r/{name}.json");
    expect(readFileSync(join(root, "src/components/godui/LICENSE.txt"), "utf8")).toContain("MIT License");
    const tokens = readFileSync(join(root, "src/styles/tokens.css"), "utf8");
    expect(tokens).toContain("--godui-primary: var(--accent)");
    const css = readFileSync(join(root, "src/styles/godui.css"), "utf8");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("animation-play-state: paused");
    expect(css).not.toMatch(/#[\da-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(/i);
  });
});