import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  StatusBadge,
  confidenceTone,
  healthTone,
  severityTone,
  statusTone,
  traceTone,
} from "@/components/ui/status-badge";

describe("StatusBadge", () => {
  it("carries meaning in text, not only colour", () => {
    render(<StatusBadge label="Red" tone="critical" />);
    expect(screen.getByText("Red")).toBeInTheDocument();
  });

  it("pairs every tone with a glyph so colour is never the only signal", () => {
    const { container } = render(<StatusBadge label="At risk" tone="critical" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("never shows an internal key to the user", () => {
    render(<StatusBadge label="risk_exposure" tone="warn" />);
    expect(screen.getByText("Risk Management")).toBeInTheDocument();
    expect(screen.queryByText("risk_exposure")).not.toBeInTheDocument();
  });

  it("maps health bands to the shared tones", () => {
    expect(healthTone("Green")).toBe("ok");
    expect(healthTone("Amber")).toBe("warn");
    expect(healthTone("Red")).toBe("critical");
  });

  it("maps confidence so weak reporting reads as a problem", () => {
    expect(confidenceTone("High")).toBe("ok");
    expect(confidenceTone("Low")).toBe("critical");
  });

  it("distinguishes critical, elevated, attention and informational severity", () => {
    expect(severityTone("Critical")).toBe("critical");
    expect(severityTone("High")).toBe("advisory");
    expect(severityTone("Medium")).toBe("warn");
    expect(severityTone("Low")).toBe("accent");
  });

  it.each(["Not verified", "No linked test case", "Uncovered"])("never marks %s as verified", (label) => {
    expect(traceTone(label)).toBe("critical");
  });

  it("preserves unknown verification states without guessing", () => {
    expect(traceTone("Verified")).toBe("ok");
    expect(traceTone("Test not run")).toBe("warn");
    expect(traceTone("Unavailable")).toBe("neutral");
  });

  it("reads workflow status consistently", () => {
    expect(statusTone("Complete")).toBe("ok");
    expect(statusTone("Blocked")).toBe("critical");
    expect(statusTone("In Progress")).toBe("warn");
  });
});
