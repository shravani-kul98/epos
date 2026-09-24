import { apiBaseUrl } from "@/config";
import { announceSaved } from "@/lib/save-feedback";

// Holds only a marker that this browser has a cookie session, never a credential.
export const SESSION_HINT_KEY = "epos.access_token";
const SESSION_HINT_MARKER = "cookie";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

// Held in memory only; after a reload the auth provider reads it again from /auth/session.
let csrfToken: string | null = null;

/** An error carrying the HTTP status so callers can distinguish 401/403/404 from a real fault. */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

/** Whether this browser signed in, so a reload knows to restore the cookie session. */
export function hasSessionHint(): boolean {
  try {
    return Boolean(window.localStorage.getItem(SESSION_HINT_KEY));
  } catch {
    return false;
  }
}

export function setSessionHint(active: boolean): void {
  try {
    if (active) {
      window.localStorage.setItem(SESSION_HINT_KEY, SESSION_HINT_MARKER);
    } else {
      window.localStorage.removeItem(SESSION_HINT_KEY);
    }
  } catch {
    // A blocked storage API must not break the session in progress.
  }
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

/** The value the API expects echoed on every write made with the session cookie. */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/** Turn a FastAPI error body into one readable sentence. */
function readErrorMessage(status: number, body: unknown): string {
  if (status >= 500) return "EPOS could not complete the request. Try again shortly.";
  if (status === 401) return "Your session has expired. Sign in again to continue.";
  if (status === 403) return "Your role does not allow this action.";
  if (status === 404) return "That record is unavailable or outside your current access.";
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : null,
        )
        .filter((item): item is string => item !== null);
      if (messages.length > 0) return messages.join(". ");
    }
  }
  return "The request could not be completed.";
}

function readFieldErrors(status: number, body: unknown): Record<string, string> {
  if (status !== 422 || !body || typeof body !== "object" || !("detail" in body) || !Array.isArray(body.detail)) return {};
  const fields: Record<string, string> = {};
  for (const item of body.detail) {
    if (item && Array.isArray(item.loc) && typeof item.msg === "string") {
      const field = item.loc[item.loc.length - 1];
      if (typeof field === "string") fields[field] = item.msg;
    }
  }
  return fields;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

let onUnauthorised: (() => void) | null = null;

/** Registered by the auth provider so an ended session is cleared once, centrally. */
export function setUnauthorisedHandler(handler: (() => void) | null): void {
  onUnauthorised = handler;
}

function header(response: Response, name: string): string | null {
  return typeof response.headers?.get === "function" ? response.headers.get(name) : null;
}

/** Re-read the session's CSRF value, which changes when another tab signs in again. */
async function reloadCsrfToken(): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl()}/auth/session`, {
      headers: { Accept: "application/json", "X-EPOS-Client": "web" },
      credentials: "same-origin",
    });
    if (!response.ok) return false;
    const state = JSON.parse(await response.text()) as { csrf_token?: unknown };
    if (typeof state.csrf_token !== "string") return false;
    csrfToken = state.csrf_token;
    return true;
  } catch {
    return false;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return send<T>(path, options, false);
}

async function send<T>(path: string, options: RequestOptions, retried: boolean): Promise<T> {
  const { method = "GET", body, signal } = options;
  const unsafe = !SAFE_METHODS.has(method.toUpperCase());
  // The web client header makes the API keep the session in an HttpOnly cookie instead of the body.
  const headers: Record<string, string> = { Accept: "application/json", "X-EPOS-Client": "web" };
  if (csrfToken && unsafe) headers["X-CSRF-Token"] = csrfToken;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "EPOS could not be reached. Check your connection and try again.");
  }

  if (response.status === 204) { announceSaved(method, path); return undefined as T; }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    if (response.status === 403 && unsafe && !retried && header(response, "X-EPOS-CSRF") === "refresh" && await reloadCsrfToken()) {
      return send<T>(path, options, true);
    }
    if (response.status === 401 && onUnauthorised) onUnauthorised();
    throw new ApiError(response.status, readErrorMessage(response.status, payload), readFieldErrors(response.status, payload));
  }

  announceSaved(method, path);
  return payload as T;
}

/** Append only the query parameters that carry a value. */
export function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}
