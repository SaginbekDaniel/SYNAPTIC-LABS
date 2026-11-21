/**
 * Network guard for the landmark worker.
 *
 * MediaPipe Tasks (1.2.x) posts usage metrics to a Google endpoint from inside the library
 * (documented in its README "Privacy Notice"; the request carries performance counters, not image
 * data). NEXORA's camera mode promises that nothing camera-related leaves the browser and that the
 * page makes no third-party requests, so the worker that hosts MediaPipe may only reach its own
 * origin. The gateway CSP (`connect-src 'self'`) enforces the same rule a second time.
 *
 * Installed only inside the dedicated worker scope — the application's own fetch is untouched.
 */

interface GuardScope {
  location: { href: string; origin: string };
  fetch: typeof fetch;
  XMLHttpRequest?: { prototype: { open: (...args: never[]) => unknown } };
  WebSocket?: unknown;
  EventSource?: unknown;
}

export class CrossOriginBlocked extends TypeError {
  constructor(readonly url: string) {
    super("cross-origin request blocked by the gesture worker");
  }
}

function resolve(scope: GuardScope, input: unknown): URL | null {
  try {
    if (typeof input === "string") return new URL(input, scope.location.href);
    if (input instanceof URL) return input;
    if (input && typeof input === "object" && "url" in input) return new URL(String((input as { url: string }).url), scope.location.href);
  } catch {
    return null;
  }
  return null;
}

export function isSameOrigin(scope: Pick<GuardScope, "location">, input: unknown): boolean {
  const url = resolve(scope as GuardScope, input);
  return url !== null && url.origin === scope.location.origin;
}

/** Returns the number of cross-origin attempts blocked so far (for diagnostics; never sent anywhere). */
export function installSameOriginGuard(scope: GuardScope): () => number {
  let blocked = 0;
  const nativeFetch = scope.fetch.bind(scope);
  scope.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (!isSameOrigin(scope, input)) {
      blocked++;
      return Promise.reject(new CrossOriginBlocked(String(resolve(scope, input) ?? input)));
    }
    return nativeFetch(input, init);
  }) as typeof fetch;

  const xhr = scope.XMLHttpRequest?.prototype;
  if (xhr) {
    const open = xhr.open;
    xhr.open = function (this: unknown, ...args: never[]) {
      if (!isSameOrigin(scope, args[1])) {
        blocked++;
        throw new CrossOriginBlocked(String(args[1]));
      }
      return (open as (...a: never[]) => unknown).apply(this, args);
    } as typeof open;
  }
  // Nothing in the worker needs push channels.
  scope.WebSocket = undefined;
  scope.EventSource = undefined;
  return () => blocked;
}
