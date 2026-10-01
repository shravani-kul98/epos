import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";
import { renderWithProviders, tokenResponse } from "@/test-utils";

afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Auth visual adapters", () => {
  it("preserves the exact sign-in endpoint and credential payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => tokenResponse() });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderWithProviders(<LoginPage />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Work email"), "pm@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "synthetic-test-pass-12");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, options] = fetchMock.mock.calls[0]! as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/auth\/login$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({ email: "pm@epos.example.com", password: "synthetic-test-pass-12" });
    expect(container.querySelectorAll('[data-slot="magic-input"]')).toHaveLength(2);
    expect(container.querySelector('.auth-form-card[data-slot="spotlight-card"]')).toBeInTheDocument();
  });

  it("keeps registration field errors linked to enhanced inputs", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByLabelText("Work email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Work email")).toHaveAttribute("aria-describedby", "email-error");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-describedby", "password-hint password-error");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    await user.click(screen.getAllByRole("button", { name: "Show password" })[0]!);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("type", "password");
  });
});