import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AskEposPage } from "@/pages/ask-epos";
import { renderWithProviders } from "@/test-utils";

const ANSWER = {
  status: "ok", matched_intent: "why_project_band", matched_question: "Explain project health",
  executive_summary: "Atlas programme needs review.", key_findings: ["A retained finding."],
  recommended_actions: ["Review the recorded handoff."], source_ids: ["HP-9062"], human_review_required: false,
  disclaimer: "Calculated from recorded evidence.", warnings: [], suggested_questions: [],
  evidence: [{ record_type: "project", record_id: "HP-9062", fields: { project_name: "Atlas programme" } }],
  conversation_id: 12, context: { project_id: "HP-9062", intent: "why_project_band" },
  project_references: [{ project_id: "HP-9062", project_name: "Atlas programme" }],
};
const SUMMARY = { id: 12, title: "Review Atlas", project_id: "HP-9062", message_count: 2, created_at: "2026-09-14T12:00:00Z", updated_at: "2026-09-14T12:00:00Z" };
const DETAIL = { ...SUMMARY, context: ANSWER.context, messages: [
  { id: 1, role: "user", content: "Explain Atlas", created_at: SUMMARY.created_at, matched_intent: null, status: null, source_ids: [], evidence: [], answer: null },
  { id: 2, role: "assistant", content: ANSWER.executive_summary, created_at: SUMMARY.created_at, matched_intent: ANSWER.matched_intent, status: "ok", source_ids: ANSWER.source_ids, evidence: ANSWER.evidence, answer: ANSWER },
] };

function mockHistory() {
  return vi.fn(async (url: string, options?: RequestInit) => {
    const path = String(url);
    const body = path.endsWith("/copilot/questions") ? [] : path.endsWith("/copilot/conversations/12") ? DETAIL
      : path.endsWith("/copilot/conversations") ? [SUMMARY] : path.endsWith("/copilot/ask") ? ANSWER
      : { projects: [{ project_id: "HP-9062", project_name: "Atlas programme" }], top_alerts: [] };
    return { ok: true, status: options?.method === "DELETE" ? 204 : 200, text: async () => options?.method === "DELETE" ? "" : JSON.stringify(body) };
  });
}

afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Persistent copilot workspace", () => {
  it("reopens complete saved answers without asking the model again", async () => {
    const api = mockHistory(); vi.stubGlobal("fetch", api);
    renderWithProviders(<AskEposPage />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Review Atlas/ }));
    expect(await screen.findByText("A retained finding.")).toBeInTheDocument();
    expect(screen.getByText("Review the recorded handoff.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Atlas programme" })).toHaveAttribute("href", "/projects/HP-9062");
    expect(api.mock.calls.some(([url]) => String(url).endsWith("/copilot/ask"))).toBe(false);
  });

  it("restores from the URL and continues the same conversation", async () => {
    const api = mockHistory(); vi.stubGlobal("fetch", api);
    renderWithProviders(<AskEposPage />, { route: "/ask?conversation=12" });
    await screen.findByText("A retained finding.");
    await userEvent.setup().type(screen.getByLabelText("Ask a question"), "Why is it at risk?{Enter}");
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).endsWith("/copilot/ask"))).toBe(true));
    const sent = api.mock.calls.find(([url]) => String(url).endsWith("/copilot/ask"));
    expect(JSON.parse(String(sent?.[1]?.body))).toMatchObject({ question: "Why is it at risk?", conversation_id: 12 });
  });

  it("lets the user explicitly reset scope without discarding the thread", async () => {
    const api = mockHistory(); vi.stubGlobal("fetch", api);
    renderWithProviders(<AskEposPage />, { route: "/ask?conversation=12" });
    await screen.findByText("A retained finding.");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Question scope"), "");
    await user.type(screen.getByLabelText("Ask a question"), "Which projects need attention?{Enter}");
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).endsWith("/copilot/ask"))).toBe(true));
    const sent = api.mock.calls.find(([url]) => String(url).endsWith("/copilot/ask"));
    expect(JSON.parse(String(sent?.[1]?.body))).toMatchObject({ conversation_id: 12, reset_context: true });
  });

  it("requires confirmation before deleting saved history", async () => {
    const api = mockHistory(); vi.stubGlobal("fetch", api);
    renderWithProviders(<AskEposPage />, { route: "/ask?conversation=12" });
    await screen.findByText("A retained finding.");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete conversation" }));
    expect(api.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(api.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(true));
    expect(await screen.findByRole("heading", { name: "What would you like to understand?" })).toBeInTheDocument();
  });

  it("does not submit during text composition and bounds the prompt", async () => {
    const api = mockHistory(); vi.stubGlobal("fetch", api);
    renderWithProviders(<AskEposPage />);
    const input = screen.getByLabelText("Ask a question");
    fireEvent.change(input, { target: { value: "A composed question" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(input).toHaveAttribute("maxlength", "1000");
    expect(api.mock.calls.some(([url]) => String(url).endsWith("/copilot/ask"))).toBe(false);
  });
});