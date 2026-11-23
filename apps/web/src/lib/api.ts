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

async function request<T>(method: string, path: string, init?: { query?: Query; body?: unknown; signal?: AbortSignal; headers?: Record<string, string> }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(withQuery(path, init?.query), {
      method,
      signal: init?.signal,
      headers: init?.body !== undefined ? { ...init.headers, "Content-Type": "application/json" } : init?.headers,
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch (err) {
    if (init?.signal?.aborted) throw init.signal.reason;
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
  if (!res.ok) {
    const env = (data as { error?: { code?: string; message?: string; request_id?: string; details?: Record<string, unknown> } } | null)?.error;
    throw new ApiError(res.status, env?.code ?? "HTTP_ERROR", env?.message ?? res.statusText, env?.request_id ?? res.headers.get("X-Request-ID"), env?.details ?? {});
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body?: unknown, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
    request<T>("POST", path, { ...options, body: body ?? {} }),
};
