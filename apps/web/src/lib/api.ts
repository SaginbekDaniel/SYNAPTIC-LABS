/** Thin fetch wrapper. Every failure becomes an ApiError carrying the server envelope. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

interface ApiAuthHooks {
  /** Session-bound CSRF token, sent on every state-changing request. */
  csrfToken: () => string | null;
  /** Called when a request is rejected because the session is missing, expired or revoked. */
  onAuthRequired: () => void;
}

let authHooks: ApiAuthHooks = { csrfToken: () => null, onAuthRequired: () => {} };

/** Wired once by app/auth.ts (kept out of this module to avoid an import cycle). */
export function configureApiAuth(hooks: ApiAuthHooks): void {
  authHooks = hooks;
}

type Query = Record<string, string | number | string[] | undefined | null>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => params.append(k, x));
    else params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(method: string, path: string, init?: { query?: Query; body?: unknown; signal?: AbortSignal }): Promise<T> {
  let res: Response;
  const headers: Record<string, string> = {};
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  const csrf = method !== "GET" ? authHooks.csrfToken() : null;
  if (csrf) headers["X-CSRF-Token"] = csrf;
  try {
    res = await fetch(withQuery(path, init?.query), {
      method,
      signal: init?.signal,
      // Same-origin only: the HttpOnly session cookie is never sent anywhere else.
      credentials: "same-origin",
      headers,
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "network unavailable", null);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, "INVALID_RESPONSE", "server returned a non-JSON response", res.headers.get("X-Request-ID"));
    }
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const env = (data as { error?: { code?: string; message?: string; request_id?: string; details?: Record<string, unknown> } } | null)?.error;
    if (res.status === 401 && env?.code === "AUTH_REQUIRED") authHooks.onAuthRequired();
    throw new ApiError(res.status, env?.code ?? "HTTP_ERROR", env?.message ?? res.statusText, env?.request_id ?? res.headers.get("X-Request-ID"), env?.details ?? {});
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} }),
};
