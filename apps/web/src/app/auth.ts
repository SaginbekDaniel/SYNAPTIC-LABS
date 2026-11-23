import { useSyncExternalStore } from "react";
import { api, configureApiAuth } from "../lib/api";
import type { AuthSession, AuthUser, SessionState } from "../lib/types";

/**
 * Client view of the server-side session. The session itself lives in an HttpOnly cookie the page
 * cannot read; this store only knows *whether* the server accepted it, who the user is, and the
 * session-bound CSRF token the server handed back. Nothing here is persisted in browser storage.
 */
export type SessionUser = AuthUser;
type SessionBody = AuthSession;

export type AuthStatus = "checking" | "authenticated" | "anonymous" | "expired" | "signed_out";

export interface AuthState {
  status: AuthStatus;
  user: SessionUser | null;
}

let state: AuthState = { status: "checking", user: null };
let csrf: string | null = null;
const listeners = new Set<() => void>();

function set(next: AuthState, token: string | null): void {
  state = next;
  csrf = token;
  listeners.forEach((l) => l());
}

// Other tabs learn about sign-in/sign-out immediately instead of on their next failed request.
const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("nexora.auth") : null;
channel?.addEventListener("message", (e: MessageEvent) => {
  if (e.data === "signed_out" && state.status === "authenticated") set({ status: "signed_out", user: null }, null);
  if (e.data === "signed_in" && state.status !== "authenticated") void restoreSession();
});

// A session can end while the tab is in the background (idle timeout, sign-out elsewhere, operator
// revocation). Re-check when the analyst comes back, so they are not left on a screen whose next
// action would fail. Throttled: at most once a minute.
let lastCheck = 0;
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible" || state.status !== "authenticated") return;
    if (Date.now() - lastCheck < 60_000) return;
    lastCheck = Date.now();
    api
      .get<SessionState>("/api/v1/auth/session")
      .then((s) => {
        if (!s.authenticated && state.status === "authenticated") set({ status: "expired", user: null }, null);
      })
      .catch(() => {
        /* offline: the next real request decides */
      });
  });
}

configureApiAuth({
  csrfToken: () => csrf,
  // Any protected request rejected with AUTH_REQUIRED means the session ended (idle/absolute expiry,
  // revocation, sign-out elsewhere). The route guard then sends the user to sign in again.
  onAuthRequired: () => {
    if (state.status === "authenticated") set({ status: "expired", user: null }, null);
  },
});

function accept(body: SessionBody): void {
  set({ status: "authenticated", user: body.user }, body.csrf_token);
}

/** Ask the server whether the browser's cookie is a live session (on load, and from other tabs). */
export async function restoreSession(): Promise<void> {
  try {
    const state = await api.get<SessionState>("/api/v1/auth/session");
    if (state.authenticated && state.session) accept(state.session);
    else set({ status: "anonymous", user: null }, null);
  } catch {
    // 401 = no session. Any other failure (network, server) is also treated as signed out: the
    // sign-in form reports connectivity problems when the user acts, instead of a dead-end screen.
    set({ status: "anonymous", user: null }, null);
  }
}

export async function signIn(username: string, password: string): Promise<void> {
  const body = await api.post<SessionBody>("/api/v1/auth/login", { username, password });
  accept(body);
  channel?.postMessage("signed_in");
}

export async function signOut(): Promise<void> {
  try {
    await api.post<void>("/api/v1/auth/logout");
  } catch {
    // The local state is cleared regardless; an unreachable server cannot keep the UI signed in.
  }
  set({ status: "signed_out", user: null }, null);
  channel?.postMessage("signed_out");
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useAuth(): AuthState {
  return useSyncExternalStore(subscribe, () => state);
}

export type Role = AuthUser["role"];
/** Mirrors nexora.auth.roles: each role may do everything the roles before it may. */
const ROLE_ORDER: readonly Role[] = ["viewer", "analyst", "admin"];

export function roleAllows(role: Role | undefined, minimum: Role): boolean {
  return role !== undefined && ROLE_ORDER.indexOf(role) >= ROLE_ORDER.indexOf(minimum);
}

/**
 * Whether the signed-in user's role permits an action. Only hides controls that would be refused:
 * the server enforces every permission on its own (B-011) and never trusts this.
 */
export function useCan(minimum: Role): boolean {
  return roleAllows(useAuth().user?.role, minimum);
}

/**
 * Where to go after signing in. Only same-origin application paths are accepted: an attacker-crafted
 * `?next=https://evil.example` or `//evil.example` falls back to the overview (open-redirect guard).
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  try {
    const url = new URL(raw, "https://nexora.invalid");
    if (url.origin !== "https://nexora.invalid" || url.pathname === "/login") return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
