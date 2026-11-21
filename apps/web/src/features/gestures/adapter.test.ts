import { describe, expect, it, vi } from "vitest";
import type { GraphCommand, GraphController } from "../../components/graph/controller";
import { GestureAdapter } from "./adapter";
import { installSameOriginGuard, isSameOrigin } from "./sameOriginGuard";

function fakeController(nodeUnderPointer: string | null = "acc-1") {
  const commands: GraphCommand[] = [];
  let dragging: string | null = null;
  const c = {
    get dragging() {
      return dragging;
    },
    nodeAt: () => nodeUnderPointer,
    dispatch: (cmd: GraphCommand) => {
      commands.push(cmd);
      if (cmd.type === "dragStart") dragging = cmd.id;
      if (cmd.type === "dragEnd" || cmd.type === "cancel") dragging = null;
      return true;
    },
  } as unknown as GraphController;
  return { c, commands };
}
const stage = () => ({ width: 1000, height: 500 });

describe("GestureAdapter", () => {
  it("converts normalised gestures to rendered-pixel viewing commands", () => {
    const { c, commands } = fakeController();
    const a = new GestureAdapter(c, stage);
    a.apply([
      { type: "pointer", x: 0.5, y: 0.5, pose: "point" },
      { type: "pan", dx: 0.1, dy: -0.1 },
      { type: "zoom", factor: 1.2, x: 0.25, y: 0.5 },
    ]);
    expect(commands).toEqual([
      { type: "hover", x: 500, y: 250 },
      { type: "pan", dx: 140, dy: -70 },
      { type: "zoomAt", factor: 1.2, x: 250, y: 250 },
    ]);
  });

  it("navigate mode: a pinch-drag never moves a node; a tap selects the node under the pointer", () => {
    const { c, commands } = fakeController("acc-7");
    const a = new GestureAdapter(c, stage);
    a.apply([{ type: "dragStart", x: 0.1, y: 0.1 }, { type: "dragMove", x: 0.4, y: 0.4 }, { type: "dragEnd" }, { type: "tap", x: 0.2, y: 0.2 }]);
    expect(commands).toEqual([{ type: "selectNode", id: "acc-7" }]);
  });

  it("a tap on empty space does nothing", () => {
    const { c, commands } = fakeController(null);
    new GestureAdapter(c, stage).apply([{ type: "tap", x: 0.2, y: 0.2 }]);
    expect(commands).toEqual([]);
  });

  it("arrange mode drags the node under the pinch; cancel undoes it", () => {
    const { c, commands } = fakeController("acc-2");
    const a = new GestureAdapter(c, stage);
    a.mode = "arrange";
    a.apply([{ type: "dragStart", x: 0.1, y: 0.2 }, { type: "dragMove", x: 0.3, y: 0.2 }, { type: "cancel", reason: "lost" }, { type: "dragMove", x: 0.9, y: 0.9 }]);
    expect(commands).toEqual([
      { type: "dragStart", id: "acc-2", x: 100, y: 100 },
      { type: "dragMove", x: 300, y: 100 },
      { type: "cancel" },
    ]);
  });

  it("never issues anything but viewing commands", () => {
    const { c, commands } = fakeController();
    const a = new GestureAdapter(c, stage);
    a.mode = "arrange";
    a.apply([
      { type: "pointer", x: 0.1, y: 0.1, pose: "pinch" },
      { type: "tap", x: 0.1, y: 0.1 },
      { type: "dragStart", x: 0.1, y: 0.1 },
      { type: "dragMove", x: 0.2, y: 0.1 },
      { type: "dragEnd" },
      { type: "pan", dx: 0.01, dy: 0 },
      { type: "zoom", factor: 0.9, x: 0.5, y: 0.5 },
      { type: "cancel", reason: "stopped" },
      { type: "pointerLost" },
    ]);
    const allowed = new Set(["hover", "hoverEnd", "selectNode", "dragStart", "dragMove", "dragEnd", "pan", "zoomAt", "cancel"]);
    expect(commands.every((cmd) => allowed.has(cmd.type))).toBe(true);
  });
});

describe("same-origin guard (landmark worker)", () => {
  const scope = () => {
    const native = vi.fn(async () => new Response("ok"));
    class Channel {
      static OPEN = 1;
      constructor(readonly url: string | URL) {}
    }
    class XHR {
      opened: unknown[] = [];
      open(...args: unknown[]) {
        this.opened = args;
      }
    }
    return {
      location: { href: "https://nexora.example/assets/worker.js", origin: "https://nexora.example" },
      fetch: native as unknown as typeof fetch,
      XMLHttpRequest: XHR as unknown as { prototype: { open: (...args: never[]) => unknown } },
      WebSocket: Channel as unknown as new (url: string | URL) => unknown,
      EventSource: Channel as unknown as new (url: string | URL) => unknown,
      native,
      XHR,
      Channel,
    };
  };

  it("lets same-origin asset loads through and refuses everything else", async () => {
    const s = scope();
    const blocked = installSameOriginGuard(s);
    await s.fetch("/vendor/mediapipe/hand_landmarker.task");
    await s.fetch(new URL("https://nexora.example/vendor/x.wasm"));
    expect(s.native).toHaveBeenCalledTimes(2);
    await expect(s.fetch("https://odml.pa.googleapis.com/v1/log", { method: "POST" })).rejects.toThrow("cross-origin");
    await expect(s.fetch("//evil.example/x")).rejects.toThrow("cross-origin");
    await expect(s.fetch(new Request("http://nexora.example/x"))).rejects.toThrow("cross-origin"); // other scheme = other origin
    expect(s.native).toHaveBeenCalledTimes(2);
    expect(blocked()).toBe(3);
  });

  it("guards XMLHttpRequest with the same rule", () => {
    const s = scope();
    installSameOriginGuard(s);
    const x = new s.XHR();
    x.open("GET", "/vendor/a.wasm");
    expect(x.opened).toEqual(["GET", "/vendor/a.wasm"]);
    expect(() => x.open("POST", "https://odml.pa.googleapis.com/v1/log")).toThrow("cross-origin");
  });

  it("allows only same-origin sockets and event streams", () => {
    const s = scope();
    const blocked = installSameOriginGuard(s);
    const WS = s.WebSocket as unknown as new (url: string) => InstanceType<typeof s.Channel>;
    const ES = s.EventSource as unknown as new (url: string) => InstanceType<typeof s.Channel>;
    // wss on the page's https origin is the same origin (the dev server's HMR socket is the case).
    const own = new WS("wss://nexora.example/hmr");
    expect(own).toBeInstanceOf(s.Channel);
    expect(own.url).toBe("wss://nexora.example/hmr");
    expect((s.WebSocket as unknown as typeof s.Channel).OPEN).toBe(1); // statics survive the guard
    expect(new ES("/events")).toBeInstanceOf(s.Channel);
    expect(() => new WS("wss://collector.example/socket")).toThrow("cross-origin");
    expect(() => new WS("ws://nexora.example/hmr")).toThrow("cross-origin"); // ws ↔ http ≠ https
    expect(() => new ES("https://collector.example/stream")).toThrow("cross-origin");
    expect(blocked()).toBe(3);
  });

  it("treats unparseable input as cross-origin", () => {
    expect(isSameOrigin({ location: { href: "https://a.example/", origin: "https://a.example" } }, "http://[bad")).toBe(false);
    expect(isSameOrigin({ location: { href: "https://a.example/", origin: "https://a.example" } }, 42)).toBe(false);
  });
});
