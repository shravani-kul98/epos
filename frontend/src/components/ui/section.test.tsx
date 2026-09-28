import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Section, StatTile } from "@/components/ui/section";

describe("Section", () => {
  it("gives a page region a heading above card level", () => {
    render(
      <Section title="Delivery position" description="Calculated as at 2026-08-25">
        <p>content</p>
      </Section>,
    );

    expect(screen.getByRole("heading", { name: "Delivery position" })).toBeInTheDocument();
    expect(screen.getByText("Calculated as at 2026-08-25")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});

describe("StatTile", () => {
  it("shows a figure with the context needed to read it", () => {
    render(<StatTile label="Health" value="50.7" caption="Red" />);

    expect(screen.getByText("Health")).toBeInTheDocument();
    expect(screen.getByText("50.7")).toBeInTheDocument();
    expect(screen.getByText("Red")).toBeInTheDocument();
  });

  it("renders as static text when it is not a filter", () => {
    render(<StatTile label="Progress" value="42%" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("becomes a pressable filter when given an action", () => {
    render(<StatTile label="Red band" value={2} onClick={() => undefined} active />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("uses tabular figures so columns of numbers align", () => {
    render(<StatTile label="Open alerts" value={16} />);
    expect(screen.getByText("16")).toHaveAttribute("data-numeric");
  });
});
