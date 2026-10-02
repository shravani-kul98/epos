import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MeetingsTab } from "@/pages/project/meetings-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "work.update", "action.manage", "risk.manage", "change.create"] })).user;
const PEOPLE = [
  { user_id: 21, full_name: "Alex Morgan", email: "alex@epos.example.com", role_label: "Project Manager", workspace_role: "project_manager" },
  { user_id: 41, full_name: "Synthetic Reviewer", email: "reviewer@epos.example.com", role_label: "External Reviewer", workspace_role: "external_reviewer" },
];

const NOTE = {
  note_id: "MN-001",
  project_id: "P-002",
  title: "Weekly delivery review",
  meeting_date: "2026-08-20",
  attendees: "Alex Morgan, Priya Raman",
  body: "Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.\nWe agreed to hold the pilot.\nRisk: synthetic supplier capacity may slip.",
};

const EXTRACTION = {
  note_id: "MN-001",
  project_id: "P-002",
  line_count: 3,
  action_count: 1,
  risk_count: 1,
  decision_count: 1,
  proposals: [
    {
      proposal_id: "MN-001-L1",
      kind: "action",
      text: "Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.",
      source_line_number: 1,
      source_line: "Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.",
      matched_phrase: "will confirm",
      suggested_owner: "Alex Morgan",
      suggested_due_date: "2026-09-04",
    },
    {
      proposal_id: "MN-001-L2",
      kind: "decision",
      text: "We agreed to hold the pilot.",
      source_line_number: 2,
      source_line: "We agreed to hold the pilot.",
      matched_phrase: "agreed to",
      suggested_owner: null,
      suggested_due_date: null,
    },
    {
      proposal_id: "MN-001-L3",
      kind: "risk",
      text: "Risk: synthetic supplier capacity may slip.",
      source_line_number: 3,
      source_line: "Risk: synthetic supplier capacity may slip.",
      matched_phrase: "risk:",
      suggested_owner: null,
      suggested_due_date: null,
    },
  ],
};

/** Route by URL so one mock serves the profile, the note list, the extraction and the promotion. */
function mockApi(promoted: unknown = { action_id: "A-0099" }) {
  return vi.fn().mockImplementation(async (url: string, init?: { method?: string }) => {
    const path = String(url);
    const ok = (body: unknown) => ({
      ok: true,
      status: init?.method === "POST" ? 201 : 200,
      text: async () => JSON.stringify(body),
    });
    if (path.includes("/auth/me")) return ok(PROFILE);
    if (path.includes("/people?purpose=")) return ok(PEOPLE);
    if (path.includes("/extraction")) return ok(EXTRACTION);
    if (path.includes("/promote")) return ok(promoted);
    return ok([NOTE]);
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

async function openNote(): Promise<void> {
  await userEvent.click(await screen.findByText("Weekly delivery review"));
  await screen.findByText("The note as written");
}

describe("meeting notes", () => {
  it("lists the meetings held on the project", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<MeetingsTab projectId="P-002" />);

    expect(await screen.findByText("Weekly delivery review")).toBeInTheDocument();
    expect(screen.getByText("Alex Morgan, Priya Raman")).toBeInTheDocument();
  });

  it("shows the line and the phrase each proposal came from", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();

    expect(await screen.findByText(/matched .will confirm./)).toBeInTheDocument();
    expect(screen.getByText(/matched .agreed to./)).toBeInTheDocument();
  });

  it("says plainly that nothing is a record yet", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();

    expect(
      await screen.findByText(/Nothing exists as a record until you accept it/),
    ).toBeInTheDocument();
  });

  it("keeps the note itself visible next to the proposals", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();

    expect(screen.getByText("The note as written")).toBeInTheDocument();
  });

  it("dismissing a proposal removes it without creating anything", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await screen.findAllByRole("button", { name: "Dismiss" });

    await userEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]!);

    await waitFor(() =>
      expect(screen.queryByText(/matched .will confirm./)).not.toBeInTheDocument(),
    );
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("/promote")),
    ).toHaveLength(0);
  });

  it("asks the reviewer to confirm the wording before creating a record", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[0]!);

    expect(await screen.findByLabelText("Wording")).toHaveValue(
      "Alex Morgan to confirm the supplier tooling capacity by 2026-09-04.",
    );
    expect(screen.getByLabelText("Owner")).toHaveValue("");
    await userEvent.click(await screen.findByRole("button", { name: "Use Alex Morgan" }));
    expect(screen.getByLabelText("Owner")).toHaveValue("21");
  });

  it("sends the reviewed wording, not the extracted line", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[0]!);

    const wording = await screen.findByLabelText("Wording");
    await userEvent.clear(wording);
    await userEvent.type(wording, "Confirm supplier tooling capacity");
    await screen.findByRole("option", { name: "Alex Morgan · Project Manager" });
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "21");
    await userEvent.click(screen.getByRole("button", { name: "Create record" }));

    await waitFor(() => {
      const promotion = fetchMock.mock.calls.find((call) =>
        String(call[0]).includes("/promote"),
      );
      expect(promotion).toBeDefined();
      expect(JSON.parse(String(promotion?.[1]?.body))).toMatchObject({
        kind: "action",
        text: "Confirm supplier tooling capacity",
        owner: "Alex Morgan",
        owner_user_id: 21,
        source_line_number: 1,
      });
    });
    expect(await screen.findByText("Created action A-0099 for Alex Morgan.")).toBeInTheDocument();
  });

  it("refuses to create a record with no owner", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[1]!);

    await userEvent.click(await screen.findByRole("button", { name: "Create record" }));

    expect(await screen.findByText("Confirm the wording and choose a registered project member before this becomes a record.")).toBeInTheDocument();
    expect(screen.getByLabelText("Owner")).toHaveAttribute("aria-invalid", "true");
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("/promote")),
    ).toHaveLength(0);
  });

  it("does not promote an extracted name without an explicit registered-member selection", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[0]!);
    await screen.findByRole("option", { name: "Alex Morgan · Project Manager" });
    await userEvent.click(screen.getByRole("button", { name: "Create record" }));
    expect(screen.getByLabelText("Owner")).toHaveAccessibleDescription(/extracted names are not confirmed assignments/);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/promote"))).toBe(false);
  });

  it.each([
    { kind: "action", index: 0, line: 1, linked: true },
    { kind: "decision", index: 1, line: 2, linked: false },
    { kind: "risk", index: 2, line: 3, linked: true },
  ])("promotes a $kind with the chosen member", async ({ kind, index, line, linked }) => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[index]!);
    await screen.findByRole("option", { name: "Synthetic Reviewer · External Reviewer" });
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "41");
    if (kind === "risk") {
      await userEvent.selectOptions(screen.getByLabelText("Probability"), "4");
      await userEvent.selectOptions(screen.getByLabelText("Impact"), "3");
    }
    await userEvent.click(screen.getByRole("button", { name: "Create record" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/promote"));
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body).toMatchObject({ kind, owner: "Synthetic Reviewer", source_line_number: line });
      // Actions and risks link the owner's account; a decision records only the name.
      if (linked) expect(body).toMatchObject({ owner_user_id: 41 });
      else expect(body).not.toHaveProperty("owner_user_id");
      if (kind === "risk") expect(body).toMatchObject({ probability: 4, impact: 3 });
      else expect(body).not.toHaveProperty("probability");
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith(`/people?purpose=${kind}`))).toBe(true);
  });

  it("asks the reviewer to score a risk instead of guessing", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[2]!);
    await screen.findByRole("option", { name: "Synthetic Reviewer · External Reviewer" });
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "41");
    await userEvent.click(screen.getByRole("button", { name: "Create record" }));

    expect(await screen.findByText("Choose the probability and impact you assess for this risk.")).toBeInTheDocument();
    expect(screen.getByLabelText("Probability")).toHaveValue("");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/promote"))).toBe(false);
  });

  it("does not offer promotions solely because the user can capture notes", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return { ok: true, status: 200, text: async () => JSON.stringify({ ...PROFILE, permissions: ["portfolio.read", "work.update"] }) };
      return api(url, init);
    }));
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await screen.findAllByRole("button", { name: "Dismiss" });
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    expect(api.mock.calls.some(([url]) => String(url).includes("/people?"))).toBe(false);
  });

  it("keeps reviewed text and selection when promotion rejects the owner", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/promote")) return { ok: false, status: 422, text: async () => JSON.stringify({ detail: [{ loc: ["body", "owner"], msg: "Select an active project member." }] }) };
      return api(url, init);
    }));
    renderWithProviders(<MeetingsTab projectId="P-002" />);
    await openNote();
    await userEvent.click((await screen.findAllByRole("button", { name: "Accept" }))[0]!);
    await screen.findByRole("option", { name: "Synthetic Reviewer · External Reviewer" });
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "41");
    await userEvent.click(screen.getByRole("button", { name: "Create record" }));
    await waitFor(() => expect(screen.getByLabelText("Owner")).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByLabelText("Owner")).toHaveAccessibleDescription(/Select an active project member/);
    expect(screen.getByLabelText("Owner")).toHaveValue("41");
    expect(screen.getByLabelText("Wording")).toHaveValue(EXTRACTION.proposals[0]!.text);
  });
});
