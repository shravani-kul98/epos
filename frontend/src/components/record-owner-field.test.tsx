import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RecordOwnerField } from "@/components/record-owner-field";
import { renderWithProviders, tokenResponse } from "@/test-utils";
import type { ProjectUserOption } from "@/types/api";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["risk.manage"] })).user;
const PEOPLE: ProjectUserOption[] = [
  { user_id: 41, full_name: "Synthetic Reviewer", email: "reviewer.one@epos.example.com", workspace_role: "external_reviewer", role_label: "External Reviewer" },
  { user_id: 42, full_name: "Synthetic Reviewer", email: "reviewer.two@epos.example.com", workspace_role: "external_reviewer", role_label: "External Reviewer" },
];

function response(body: unknown, status = 200) {
  return { ok: status < 400, status, text: async () => JSON.stringify(body) };
}

function mockApi(people = PEOPLE, permissions: string[] = PROFILE.permissions) {
  return vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me")) return response({ ...PROFILE, permissions });
    if (url.endsWith("/projects/P-002/people?purpose=risk")) return response(people);
    throw new Error(`Unexpected request: ${url}`);
  });
}

function OwnerForm({ initial = null, onChange = () => undefined, required = false, error }: {
  initial?: string | null;
  onChange?: (name: string | null, userId: number | null) => void;
  required?: boolean;
  error?: string;
}): JSX.Element {
  const [value, setValue] = useState(initial);
  return <RecordOwnerField projectId="P-002" purpose="risk" label="Mitigation owner" id="owner"
    value={value} required={required} error={error}
    onChange={(name, userId) => { setValue(name); onChange(name, userId); }} />;
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
  vi.stubGlobal("fetch", mockApi());
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("RecordOwnerField", () => {
  it("loads purpose-scoped reviewers without requiring work.manage and sends the name with the account", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const onChange = vi.fn();
    renderWithProviders(<OwnerForm onChange={onChange} />);
    const user = userEvent.setup();
    await screen.findByRole("option", { name: /reviewer.two@epos.example.com/ });
    await user.selectOptions(screen.getByLabelText("Mitigation owner"), "42");
    expect(onChange).toHaveBeenLastCalledWith("Synthetic Reviewer", 42);
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("42");
    expect(screen.getByRole("option", { name: /reviewer.two@epos.example.com/ })).toHaveProperty("selected", true);
    expect(api.mock.calls.some(([url]) => url.includes("/assignees"))).toBe(false);
    expect(screen.getByText(/Only the name is saved/)).toBeInTheDocument();
  });

  it("recognises a recorded name that matches exactly one member and hides unneeded addresses", async () => {
    const unique: ProjectUserOption[] = [
      { user_id: 51, full_name: "Eli Tan", email: "eli@epos.example.com", workspace_role: "engineer", role_label: "Engineer" },
      { user_id: 52, full_name: "Mara Holt", email: "mara@epos.example.com", workspace_role: "pmo_analyst", role_label: "PMO Analyst" },
    ];
    vi.stubGlobal("fetch", mockApi(unique));
    renderWithProviders(<OwnerForm initial="Eli Tan" />);
    await screen.findByRole("option", { name: "Eli Tan · Engineer" });
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("51");
    expect(screen.queryByRole("option", { name: /recorded name/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /@epos.example.com/ })).not.toBeInTheDocument();
  });

  it.each([
    ["Historical Owner", "Historical Owner — recorded name, not a current project member"],
    ["Synthetic Reviewer", "Synthetic Reviewer — recorded name; choose the matching member"],
  ])("preserves %s as a disabled recorded name until explicitly changed", async (initial, label) => {
    const onChange = vi.fn();
    renderWithProviders(<OwnerForm initial={initial} onChange={onChange} />);
    await screen.findByRole("option", { name: /reviewer.one@epos.example.com/ });
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("historical");
    expect(screen.getByRole("option", { name: label })).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByLabelText("Mitigation owner"), "41");
    expect(onChange).toHaveBeenLastCalledWith("Synthetic Reviewer", 41);
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("41");
  });

  it("allows clearing an optional historical owner to null", async () => {
    const onChange = vi.fn();
    renderWithProviders(<OwnerForm initial="Historical Owner" onChange={onChange} />);
    await screen.findByRole("option", { name: /reviewer.one@epos.example.com/ });
    await userEvent.selectOptions(screen.getByLabelText("Mitigation owner"), "");
    expect(onChange).toHaveBeenLastCalledWith(null, null);
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("");
  });

  it("associates owner validation errors with the required picker", async () => {
    renderWithProviders(<OwnerForm required error="Choose a registered project member." />);
    await screen.findByRole("option", { name: /reviewer.one@epos.example.com/ });
    expect(screen.getByLabelText("Mitigation owner")).toBeRequired();
    expect(screen.getByLabelText("Mitigation owner")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Mitigation owner")).toHaveAttribute("aria-describedby", "owner-hint owner-error");
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a registered project member.");
  });

  it("preserves the current name on lookup failure and supports retry", async () => {
    let failing = true;
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn((url: string) =>
      url.includes("/people?") && failing ? Promise.resolve(response({}, 503)) : api(url),
    ));
    const onChange = vi.fn();
    renderWithProviders(<OwnerForm initial="Historical Owner" onChange={onChange} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("EPOS could not complete the request");
    expect(screen.getByLabelText("Mitigation owner")).toBeDisabled();
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("historical");
    failing = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry people" }));
    await screen.findByRole("option", { name: /reviewer.one@epos.example.com/ });
    expect(screen.getByLabelText("Mitigation owner")).toBeEnabled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not replace a selected name when the person disappears from refreshed options", async () => {
    let people = PEOPLE;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url.endsWith("/auth/me") ? PROFILE : people)));
    const onChange = vi.fn();
    renderWithProviders(<OwnerForm onChange={onChange} />);
    await screen.findByRole("option", { name: /reviewer.one@epos.example.com/ });
    await userEvent.selectOptions(screen.getByLabelText("Mitigation owner"), "41");
    people = [];
    await userEvent.click(screen.getByRole("button", { name: "Refresh people" }));
    await waitFor(() => expect(screen.getByLabelText("Mitigation owner")).toHaveValue("historical"));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("option", { name: /Synthetic Reviewer — recorded name/ })).toBeDisabled();
  });

  it("gives permission-aware empty-pool advice without a link that can discard a dirty form", async () => {
    vi.stubGlobal("fetch", mockApi([], ["risk.manage", "project_members.manage"]));
    renderWithProviders(<OwnerForm />);
    expect(await screen.findByText(/Finish or cancel this form before adding a person in Team members/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("does not fetch people before login", () => {
    window.localStorage.clear();
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<OwnerForm />);
    expect(api).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Mitigation owner")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /people/ })).not.toBeInTheDocument();
  });

  it("does not fetch people for an authenticated user without the relevant permission", async () => {
    const api = mockApi(PEOPLE, ["portfolio.read"]);
    vi.stubGlobal("fetch", api);
    renderWithProviders(<OwnerForm />);
    await waitFor(() => expect(api).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.some(([url]) => url.includes("/people?"))).toBe(false);
    expect(screen.getByLabelText("Mitigation owner")).toBeDisabled();
  });
});