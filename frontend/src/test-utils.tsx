import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";

interface RenderOptions {
  route?: string;
  queryClient?: QueryClient;
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/** Render a component inside the providers the application relies on, with retries disabled. */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", queryClient = createTestQueryClient() }: RenderOptions = {},
): ReturnType<typeof render> {
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>{ui}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

/** A web-client token response shaped like the API's: the token itself travels in a cookie. */
export function tokenResponse(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    access_token: null,
    token_type: "bearer",
    expires_in_seconds: 3600,
    csrf_token: "test-csrf-token",
    user: {
      id: 1,
      email: "pm@epos.example.com",
      full_name: "Test Manager",
      role: "project_manager",
      role_label: "Project Manager",
      job_title: null,
      is_active: true,
      permissions: ["portfolio.read", "project.create", "copilot.ask"],
      created_at: "2026-08-25T00:00:00Z",
      last_login_at: null,
      ...overrides,
    },
  });
}
