import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getCsrfToken, setCsrfToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { createTestQueryClient, renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["work.manage"] })).user;
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });
const refused = (status: number) => ({ ok: false, status, text: async () => "{}" });
const noContent = () => ({ ok: true, status: 204, text: async () => "" });

/** What GET /auth/session reports when the current token expires the given seconds from now. */
function sessionState(secondsLeft: number) {
  return {
    csrf_token: "csrf-restored",
    expires_at: new Date(Date.now() + secondsLeft * 1000).toISOString(),
    session_expires_at: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
  };
}

function header(init: RequestInit | undefined, name: string): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.[name];
}

function Probe(): JSX.Element {
  const { status, can } = useAuth();
  return <p>{status === "authenticated" ? can("work.manage") ? "Can manage work" : "Read only" : status}</p>;
}

function SignOutProbe(): JSX.Element {
  const { status, signOut } = useAuth();
  return <><p>{status}</p><button type="button" onClick={() => void signOut()}>Sign out</button></>;
}

beforeEach(() => { window.localStorage.setItem("epos.access_token", "cookie"); });
afterEach(() => { window.localStorage.clear(); setCsrfToken(null); vi.unstubAllGlobals(); });

describe("Current permission refresh", () => {
  it("refreshes a changed role on focus and clears old authorized data", async () => {
    let profile = PROFILE;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ok(url.endsWith("/auth/session") ? sessionState(3000) : profile)));
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["private-project"], { project_id: "P-SYNTHETIC" });
    renderWithProviders(<Probe />, { queryClient });
    await screen.findByText("Can manage work");
    profile = { ...PROFILE, role: "engineer", permissions: ["work.update"] };
    fireEvent(window, new Event("focus"));
    expect(await screen.findByText("Read only")).toBeInTheDocument();
    expect(queryClient.getQueryData(["private-project"])).toBeUndefined();
  });

  it("clears the session if the account was disabled", async () => {
    let disabled = false;
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      disabled ? refused(403) : ok(url.endsWith("/auth/session") ? sessionState(3000) : PROFILE),
    ));
    renderWithProviders(<Probe />);
    await screen.findByText("Can manage work");
    disabled = true;
    fireEvent(window, new Event("focus"));
    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(window.localStorage.getItem("epos.access_token")).toBeNull();
    expect(getCsrfToken()).toBeNull();
  });

  it("honours sign-out in another tab without another request", async () => {
    const api = vi.fn(async (url: string) => ok(url.endsWith("/auth/session") ? sessionState(3000) : PROFILE));
    vi.stubGlobal("fetch", api);
    renderWithProviders(<Probe />);
    await screen.findByText("Can manage work");
    const requestsBefore = api.mock.calls.length;
    window.localStorage.removeItem("epos.access_token");
    fireEvent(window, new StorageEvent("storage", { key: "epos.access_token", newValue: null }));
    await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
    expect(api.mock.calls).toHaveLength(requestsBefore);
  });
});

describe("Session renewal", () => {
  it("restores the CSRF token after a reload and renews a session about to expire", async () => {
    const api = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/session")) return ok(sessionState(60));
      if (url.endsWith("/auth/refresh") && init?.method === "POST") {
        return ok({ access_token: null, token_type: "bearer", expires_in_seconds: 3600, user: PROFILE, csrf_token: "csrf-renewed" });
      }
      return ok(PROFILE);
    });
    vi.stubGlobal("fetch", api);
    renderWithProviders(<Probe />);
    await screen.findByText("Can manage work");
    expect(getCsrfToken()).toBe("csrf-restored");

    fireEvent(window, new Event("focus"));

    await waitFor(() => expect(getCsrfToken()).toBe("csrf-renewed"));
    const renewal = api.mock.calls.find(([url]) => url.endsWith("/auth/refresh"));
    expect(renewal?.[1]?.method).toBe("POST");
    expect(header(renewal?.[1], "X-CSRF-Token")).toBe("csrf-restored");
  });

  it("leaves a session with time to spare alone", async () => {
    const api = vi.fn(async (url: string) => ok(url.endsWith("/auth/session") ? sessionState(3000) : PROFILE));
    vi.stubGlobal("fetch", api);
    renderWithProviders(<Probe />);
    await screen.findByText("Can manage work");

    fireEvent(window, new Event("focus"));

    await waitFor(() => expect(api.mock.calls.filter(([url]) => url.endsWith("/auth/session"))).toHaveLength(2));
    expect(api.mock.calls.some(([url]) => url.endsWith("/auth/refresh"))).toBe(false);
  });

  it("signs this tab out when the session has reached its maximum length", async () => {
    const api = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh") && init?.method === "POST") return refused(401);
      return ok(url.endsWith("/auth/session") ? sessionState(60) : PROFILE);
    });
    vi.stubGlobal("fetch", api);
    renderWithProviders(<Probe />);
    await screen.findByText("Can manage work");

    fireEvent(window, new Event("focus"));

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(window.localStorage.getItem("epos.access_token")).toBeNull();
    expect(api.mock.calls.some(([url]) => url.endsWith("/auth/logout"))).toBe(false);
  });
});

describe("Session restore and sign-out", () => {
  it("stays signed in without a CSRF token when the session details cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/auth/session") ? refused(500) : ok(PROFILE)));
    renderWithProviders(<Probe />);
    expect(await screen.findByText("Can manage work")).toBeInTheDocument();
    expect(getCsrfToken()).toBeNull();
  });

  it("drops a stale hint on load without calling logout", async () => {
    const api = vi.fn(async (url: string) => url.endsWith("/auth/logout") ? noContent() : refused(401));
    vi.stubGlobal("fetch", api);
    renderWithProviders(<Probe />);
    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(window.localStorage.getItem("epos.access_token")).toBeNull();
    expect(api.mock.calls.some(([url]) => url.endsWith("/auth/logout"))).toBe(false);
  });

  it("ends the session through the API when the user signs out", async () => {
    const api = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/logout") && init?.method === "POST") return noContent();
      return ok(url.endsWith("/auth/session") ? sessionState(3000) : PROFILE);
    });
    vi.stubGlobal("fetch", api);
    renderWithProviders(<SignOutProbe />);
    await screen.findByText("authenticated");

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    const logout = api.mock.calls.find(([url]) => url.endsWith("/auth/logout"));
    expect(logout?.[1]?.method).toBe("POST");
    expect(header(logout?.[1], "X-CSRF-Token")).toBe("csrf-restored");
    expect(window.localStorage.getItem("epos.access_token")).toBeNull();
    expect(getCsrfToken()).toBeNull();
  });
});
