import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskEposPage } from "@/pages/ask-epos";
import { renderWithProviders } from "@/test-utils";

function answer(overrides: Record<string, unknown> = {}): unknown {
  return {
    status: "ok",
    matched_intent: "projects_needing_attention",
    matched_question: "Which projects need attention this week?",
    executive_summary: "Two projects require immediate attention.",
    key_findings: ["Supplier Decarbonisation scores 50.7 and is in the Red band."],
    recommended_actions: ["Confirm the recovery plan with the project manager."],
    source_ids: ["P-002"],
    human_review_required: true,
    disclaimer: "AI-generated decision-support draft; human review required.",
    warnings: [],
    evidence: [
      {
        record_type: "risk",
        record_id: "R-2001",
        fields: { risk_name: "Supplier data quality incomplete", status: "Open" },
      },
    ],
    suggested_questions: [],
    conversation_id: 7,
    ...overrides,
  };
}

/** Route by URL so a single mock can serve both the question list and the answer. */
function mockApi(answerBody: unknown) {
  return vi.fn().mockImplementation(async (url: string) => {
    if (String(url).includes("/copilot/questions")) {
      return {
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify([
            { intent: "projects_needing_attention", question: "Which projects need attention this week?", requires_context: null },
          ]),
      };
    }
    if (String(url).includes("/copilot/ask")) {
      return { ok: true, status: 200, text: async () => JSON.stringify(answerBody) };
    }
    return { ok: true, status: 200, text: async () => JSON.stringify({ projects: [], top_alerts: [] }) };
  });
}

describe("AskEposPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("leads with a free-text composer, not a fixed question list", () => {
    vi.stubGlobal("fetch", mockApi(answer()));
    renderWithProviders(<AskEposPage />);

    expect(screen.getByLabelText("Ask a question")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ask EPOS/ })).toBeInTheDocument();
  });

  it("answers a question asked in the user's own words", async () => {
    vi.stubGlobal("fetch", mockApi(answer()));
    renderWithProviders(<AskEposPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Ask a question"), "which projects are struggling?");
    await user.click(screen.getByRole("button", { name: /Ask EPOS/ }));

    expect(await screen.findByText("Two projects require immediate attention.")).toBeInTheDocument();
    expect(screen.getByText(/Supplier Decarbonisation scores 50.7/)).toBeInTheDocument();
  });

  it("keeps the conversation so earlier questions stay visible", async () => {
    vi.stubGlobal("fetch", mockApi(answer()));
    renderWithProviders(<AskEposPage />);
    const user = userEvent.setup();

    const box = screen.getByLabelText("Ask a question");
    await user.type(box, "first question{Enter}");
    await screen.findByText("Two projects require immediate attention.");
    await user.type(box, "second question{Enter}");

    await waitFor(() => {
      expect(screen.getByText("first question")).toBeInTheDocument();
      expect(screen.getByText("second question")).toBeInTheDocument();
    });
  });

  it("marks an answer for review and offers its sources", async () => {
    vi.stubGlobal("fetch", mockApi(answer()));
    renderWithProviders(<AskEposPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Ask a question"), "status please{Enter}");
    expect(
      await screen.findByText("AI-generated decision-support draft; human review required."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Sources/ }));
    expect(await screen.findByText("Supplier data quality incomplete")).toBeInTheDocument();
  });

  it("explains what it can help with instead of reporting a routing failure", async () => {
    vi.stubGlobal(
      "fetch",
      mockApi(
        answer({
          status: "clarification",
          executive_summary: "I can look at delivery status, milestones at risk and portfolio summaries.",
          key_findings: [],
          recommended_actions: [],
          evidence: [],
          suggested_questions: ["Which projects need attention this week?"],
        }),
      ),
    );
    renderWithProviders(<AskEposPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Ask a question"), "what is the weather{Enter}");

    expect(await screen.findByText(/I can look at delivery status/)).toBeInTheDocument();
    expect(screen.queryByText(/intent/i)).not.toBeInTheDocument();
  });

  it("keeps project information intact when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes("/copilot/ask")) {
          return { ok: false, status: 500, text: async () => JSON.stringify({ detail: "boom" }) };
        }
        return { ok: true, status: 200, text: async () => JSON.stringify([]) };
      }),
    );
    renderWithProviders(<AskEposPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Ask a question"), "status please{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your project information is unchanged.",
    );
    expect(screen.getByLabelText("Ask a question")).toHaveValue("status please");
    expect(screen.getByRole("button",{name:"Retry question"})).toBeInTheDocument();
  });

  it("labels a deterministic lookup separately from AI explanation",async()=>{
    vi.stubGlobal("fetch",mockApi(answer({human_review_required:false,disclaimer:"Calculated from recorded data."})));
    renderWithProviders(<AskEposPage/>);
    await userEvent.setup().type(screen.getByLabelText("Ask a question"),"list projects{Enter}");
    expect(await screen.findByRole("heading",{name:"Calculated answer"})).toBeInTheDocument();
    expect(screen.queryByRole("heading",{name:"AI decision-support explanation"})).not.toBeInTheDocument();
  });
});
