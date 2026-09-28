import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreCard } from "@/components/ui/score-card";
import type { FactorBreakdown } from "@/types/api";

const FACTORS: FactorBreakdown[] = [
  {
    key: "schedule_health",
    label: "Schedule Health",
    description: "Milestone slip against baseline.",
    score: 42.5,
    weight: 0.3,
    weighted_contribution: 12.75,
    explanations: ["Two milestones are forecast beyond baseline."],
  },
];

describe("ScoreCard", () => {
  it("shows the score exactly as the API calculated it", () => {
    render(
      <ScoreCard
        title="Project health"
        score={50.7}
        band="Red"
        tone="critical"
        factors={FACTORS}
        sourceIds={["P-002", "M-014"]}
        limitations={["Analysis uses a fixed as-at date."]}
        asOfDate="2026-08-25"
      />,
    );

    expect(screen.getByText("50.7")).toBeInTheDocument();
    expect(screen.getByText("Red")).toBeInTheDocument();
    expect(screen.getByText("Schedule Health")).toBeInTheDocument();
  });

  it("cites the records behind the number", () => {
    render(
      <ScoreCard
        title="Project health"
        score={50.7}
        band="Red"
        tone="critical"
        factors={FACTORS}
        sourceIds={["P-002", "M-014"]}
        limitations={[]}
        asOfDate="2026-08-25"
      />,
    );

    expect(screen.getByText("P-002")).toBeInTheDocument();
    expect(screen.getByText("M-014")).toBeInTheDocument();
  });

  it("states its assumptions", () => {
    render(
      <ScoreCard
        title="Project health"
        score={50.7}
        band="Red"
        tone="critical"
        factors={FACTORS}
        sourceIds={[]}
        limitations={["Analysis uses a fixed as-at date."]}
        asOfDate="2026-08-25"
      />,
    );

    expect(screen.getByText("Analysis uses a fixed as-at date.")).toBeInTheDocument();
  });
});
