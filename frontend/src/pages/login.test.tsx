import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "@/pages/login";
import { getCsrfToken } from "@/lib/api";
import { createTestQueryClient, renderWithProviders, tokenResponse } from "@/test-utils";

describe("LoginPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("asks for credentials", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("offers a route to registration", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<LoginPage />);
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register");
  });

  it("lets the user reveal the password they typed", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<LoginPage />);
    const user = userEvent.setup();

    const field = screen.getByLabelText("Password");
    expect(field).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  });

  it("does not reveal whether the account exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ detail: "No user with that address" }),
      }),
    );

    renderWithProviders(<LoginPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Work email"), "someone@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    });
    expect(screen.getByRole("alert")).not.toHaveTextContent("No user with that address");
  });

  it.each([
    { status: 403, body: { detail: "This account has been disabled." }, message: "This account has been disabled." },
    { status: 503, body: {}, message: "EPOS could not complete the request. Try again shortly." },
  ])("explains a $status refusal instead of blaming the password", async ({ status, body, message }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status, text: async () => JSON.stringify(body) }),
    );

    renderWithProviders(<LoginPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Work email"), "someone@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "a-password-123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(message);
    });
    expect(screen.getByRole("alert")).not.toHaveTextContent("Email or password is incorrect.");
  });

  it("keeps only a session marker in storage after a successful sign-in", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => tokenResponse() });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["projects"], [{ project_id: "P-PRIVATE" }]);
    renderWithProviders(<LoginPage />, { queryClient });
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Work email"), "pm@epos.example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(window.localStorage.getItem("epos.access_token")).toBe("cookie");
      expect(queryClient.getQueryData(["projects"])).toBeUndefined();
    });
    expect(getCsrfToken()).toBe("test-csrf-token");
    expect(fetchMock.mock.calls[0][1].headers["X-EPOS-Client"]).toBe("web");
  });
});
