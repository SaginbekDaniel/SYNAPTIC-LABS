import { afterEach, describe, expect, it, vi } from "vitest";
import { roleAllows, safeNext } from "./auth";
import { api, ApiError, configureApiAuth } from "../lib/api";

describe("safeNext (open-redirect guard)", () => {
  it("keeps same-origin application paths, query and hash", () => {
    expect(safeNext("/alerts?band=high#row-3")).toBe("/alerts?band=high#row-3");
    expect(safeNext("/alerts/123e4567-e89b-12d3-a456-426614174000")).toBe("/alerts/123e4567-e89b-12d3-a456-426614174000");
  });
  it.each([null, undefined, "", "alerts", "https://evil.example/", "//evil.example/x", "/\\evil.example", "javascript:alert(1)", "/login", "/login?next=/x"])(
    "falls back to the overview for %s",
    (raw) => expect(safeNext(raw)).toBe("/"),
  );
});

describe("api client and the session", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(status: number, body: unknown) {
    const fetchMock = vi.fn(async () => new Response(body === null ? null : JSON.stringify(body), { status }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("sends the session CSRF token on writes only, with same-origin credentials", async () => {
    configureApiAuth({ csrfToken: () => "csrf-abc", onAuthRequired: () => {} });
    const fetchMock = stubFetch(200, {});
    await api.post("/api/v1/lab/datasets", { suite: "demo-v1" });
    await api.get("/api/v1/datasets");
    const [, write] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [, read] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect((write.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-abc");
    expect((read.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
    expect(write.credentials).toBe("same-origin");
  });

  it("reports an ended session exactly when the server says AUTH_REQUIRED", async () => {
    const onAuthRequired = vi.fn();
    configureApiAuth({ csrfToken: () => null, onAuthRequired });
    stubFetch(401, { error: { code: "AUTH_REQUIRED", message: "authentication required", request_id: "r1", details: {} } });
    await expect(api.get("/api/v1/datasets")).rejects.toBeInstanceOf(ApiError);
    expect(onAuthRequired).toHaveBeenCalledTimes(1);
    stubFetch(401, { error: { code: "INVALID_CREDENTIALS", message: "invalid user name or password", request_id: "r2", details: {} } });
    await expect(api.post("/api/v1/auth/login", {})).rejects.toMatchObject({ status: 401, code: "INVALID_CREDENTIALS" });
    expect(onAuthRequired).toHaveBeenCalledTimes(1);
  });

  it("treats 204 No Content as success", async () => {
    stubFetch(204, null);
    await expect(api.post("/api/v1/auth/logout")).resolves.toBeUndefined();
  });
});

describe("roleAllows (mirrors nexora.auth.roles; display only, the server enforces)", () => {
  it.each([
    ["viewer", "viewer", true],
    ["viewer", "analyst", false],
    ["analyst", "analyst", true],
    ["analyst", "admin", false],
    ["admin", "analyst", true],
    ["admin", "admin", true],
  ] as const)("%s may act as %s: %s", (role, minimum, allowed) => expect(roleAllows(role, minimum)).toBe(allowed));
  it("allows nothing without a signed-in user", () => expect(roleAllows(undefined, "viewer")).toBe(false));
});
