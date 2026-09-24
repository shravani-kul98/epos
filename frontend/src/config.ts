/**
 * Resolve the API origin.
 *
 * When EPOS is served by the backend itself, a relative prefix keeps the app portable across
 * hosts. During Vite development the frontend runs on its own port, so it targets the local API.
 */
export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured.replace(/\/$/, "");

  if (typeof window !== "undefined" && window.location.port === "5173") {
    return "http://127.0.0.1:8000/api/v1";
  }
  return "/api/v1";
}

export const PRODUCT_NAME = "EPOS";
export const PRODUCT_DESCRIPTION = "Engineering Portfolio Operating System";
export const WORKSPACE_NAME = "Engineering Workspace";
export const VALUE_STATEMENT = "Plan, control and deliver engineering work with clarity.";
export const WORK_REFRESH_INTERVAL_MS = 30_000;
// Scores change only when someone records work, and every write refreshes them at once.
export const ANALYSIS_REFRESH_INTERVAL_MS = 120_000;
export const NOTIFICATION_REFRESH_INTERVAL_MS = 60_000;
