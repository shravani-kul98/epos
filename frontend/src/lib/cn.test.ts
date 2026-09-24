import { describe, expect, it } from "vitest";
import { cn } from "@/lib/cn";

describe("Semantic class merging", () => {
  it.each(["meta", "table", "body", "card", "section", "title", "kpi", "identifier"])(
    "keeps the foreground color alongside the %s typography token",
    (size) => {
      expect(cn("text-ink-onaccent", `text-${size}`)).toBe(`text-ink-onaccent text-${size}`);
      expect(cn(`text-${size}`, "text-critical")).toBe(`text-${size} text-critical`);
    },
  );

  it("still lets intentional size and color overrides win independently", () => {
    expect(cn("text-body text-critical", "text-meta text-ok")).toBe("text-meta text-ok");
  });
});