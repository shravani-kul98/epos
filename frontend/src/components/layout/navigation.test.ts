import { describe, expect, it } from "vitest";

import { navigationFor } from "@/components/layout/navigation";

describe("navigation", () => {
  it("hides areas a role cannot use", () => {
    const engineer = new Set(["portfolio.read", "work.update", "copilot.ask"]);
    const labels = navigationFor((permission) => engineer.has(permission)).map((item) => item.label);

    expect(labels).toContain("My Work");
    expect(labels).toContain("Projects");
    expect(labels).toContain("Ask EPOS");
    expect(labels).not.toContain("Team & Access");
    expect(labels).not.toContain("Scenarios");
    expect(labels).not.toContain("Executive report");
    expect(labels[0]).toBe("Overview");
  });

  it("gives an administrator every area", () => {
    const labels = navigationFor(() => true).map((item) => item.label);

    expect(labels).toContain("Team & Access");
    expect(labels).toContain("Scenarios");
    expect(labels).toContain("Change requests");
    expect(labels).toContain("Executive summary");
  });

  it("keeps personal areas reachable regardless of portfolio access", () => {
    expect(navigationFor(() => false).map((item) => item.label)).toEqual([
      "Overview",
      "My Work",
      "Inbox",
      "Calendar",
    ]);
  });

  it("uses business wording, never an internal key", () => {
    for (const item of navigationFor(() => true)) {
      expect(item.label).not.toMatch(/_/);
      expect(item.label[0]).toEqual(item.label[0]?.toUpperCase());
    }
  });
});
