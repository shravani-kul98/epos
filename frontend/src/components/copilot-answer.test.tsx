import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CopilotAnswerCard } from "@/components/copilot-answer";
import { renderWithProviders } from "@/test-utils";
import type { CopilotAnswer } from "@/types/api";

const ANSWER: CopilotAnswer = {
  status: "ok",
  matched_intent: "list_projects",
  matched_question: "Which projects are tech projects?",
  executive_summary: "Two projects are recorded in the matching domains.",
  key_findings: [],
  recommended_actions: [],
  source_ids: [],
  human_review_required: false,
  disclaimer: "Calculated from current records.",
  warnings: [],
  evidence: [],
  suggested_questions: [],
  conversation_id: null,
  applied_filters: [
    { field: "domain", label: "Domain", values: ["Embedded Software", "IT Systems"], excluded: false, interpreted_from: "tech" },
  ],
};

describe("CopilotAnswerCard filters", () => {
  it("names the applied values and the phrase they were read from", () => {
    renderWithProviders(<CopilotAnswerCard answer={ANSWER} onOpenSources={() => {}} onFollowUp={() => {}} busy={false} />);

    const filters = within(screen.getByRole("list", { name: "Filters applied to this answer" }));
    expect(filters.getByText(/Embedded Software, IT Systems/)).toBeInTheDocument();
    expect(filters.getByText("(read from “tech”)")).toBeInTheDocument();
  });
});
