import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegisterPage } from "@/pages/register";
import { assessPassword } from "@/components/ui/password-input";
import { renderWithProviders, tokenResponse } from "@/test-utils";

describe("RegisterPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never offers a role picker", () => {
    vi.stubGlobal("fetch", vi.fn());
    const { container } = renderWithProviders(<RegisterPage />);
    // A self-registering user must not be able to choose their own access level.
    expect(container.querySelector("select")).toBeNull();
    expect(screen.queryByLabelText(/^role$/i)).not.toBeInTheDocument();
  });

  it("rejects a weak password and keeps everything already entered", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Full name"), "Alex Morgan");
    await user.type(screen.getByLabelText("Work email"), "alex@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Use at least 12 characters.")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toHaveValue("Alex Morgan");
    expect(screen.getByLabelText("Work email")).toHaveValue("alex@epos.example.com");
  });

  it("requires both passwords to match", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Full name"), "Alex Morgan");
    await user.type(screen.getByLabelText("Work email"), "alex@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "Delivery-Plan-2026!");
    await user.type(screen.getByLabelText("Confirm password"), "Delivery-Plan-2027!");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Both passwords must match.")).toBeInTheDocument();
  });

  it("sends no role to the API when registering", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 201, text: async () => tokenResponse() });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Full name"), "Alex Morgan");
    await user.type(screen.getByLabelText("Work email"), "alex@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "Delivery-Plan-2026!");
    await user.type(screen.getByLabelText("Confirm password"), "Delivery-Plan-2026!");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).not.toHaveProperty("role");
    expect(body).not.toHaveProperty("invitation_code");
    expect(body.email).toBe("alex@epos.example.com");
  });

  it("registers an invited person with the address and code from the link", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 201, text: async () => tokenResponse({ role: "engineer" }) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<RegisterPage />, {
      route: "/register?invite=Invite-Code-1234567890&email=invited%40epos.example.com",
    });
    const user = userEvent.setup();

    expect(screen.getByText(/You were invited to this workspace/)).toBeInTheDocument();
    const email = screen.getByLabelText("Work email");
    expect(email).toHaveValue("invited@epos.example.com");
    expect(email).toHaveAttribute("readonly");

    await user.type(screen.getByLabelText("Full name"), "Alex Morgan");
    await user.type(screen.getByLabelText("Password"), "Delivery-Plan-2026!");
    await user.type(screen.getByLabelText("Confirm password"), "Delivery-Plan-2026!");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      full_name: "Alex Morgan",
      email: "invited@epos.example.com",
      password: "Delivery-Plan-2026!",
      job_title: null,
      invitation_code: "Invite-Code-1234567890",
    });
  });

  it.each([
    { status: 403, detail: "Self-registration is turned off.", shown: "Sign-up is not open for this address. Ask a workspace administrator for an account." },
    { status: 409, detail: "An account could not be created with these details. If you already have one, sign in.", shown: "An account could not be created with these details. If you already have one, sign in." },
    { status: 429, detail: "Too many accounts were requested from this network. Try again later.", shown: "Too many accounts were requested from this network. Try again later." },
  ])("explains a $status refusal", async ({ status, detail, shown }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status, text: async () => JSON.stringify({ detail }) }),
    );

    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Full name"), "Alex Morgan");
    await user.type(screen.getByLabelText("Work email"), "alex@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "Delivery-Plan-2026!");
    await user.type(screen.getByLabelText("Confirm password"), "Delivery-Plan-2026!");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(shown)).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toHaveValue("alex@epos.example.com");
  });
});

describe("assessPassword", () => {
  it("treats a long single-character password as weak", () => {
    expect(assessPassword("aaaaaaaaaaaaaaaa").score).toBeLessThanOrEqual(1);
  });

  it("rewards length and variety", () => {
    expect(assessPassword("Delivery-Plan-2026!").score).toBeGreaterThanOrEqual(4);
  });
});
