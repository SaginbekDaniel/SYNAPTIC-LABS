import { describe, expect, it, vi } from "vitest";
import { routeInformationalStderr } from "./workerConsole";

describe("routeInformationalStderr (landmark worker)", () => {
  const target = () => {
    const error = vi.fn();
    const info = vi.fn();
    return { c: { error, info } as Pick<Console, "error" | "info">, error, info };
  };

  it("sends the runtime's informational lines to console.info", () => {
    const { c, error, info } = target();
    routeInformationalStderr(c);
    c.error("INFO: Created TensorFlow Lite XNNPACK delegate for CPU.");
    expect(info).toHaveBeenCalledWith("INFO: Created TensorFlow Lite XNNPACK delegate for CPU.");
    expect(error).not.toHaveBeenCalled();
  });

  it("keeps real errors, non-string arguments and look-alikes on console.error", () => {
    const { c, error, info } = target();
    routeInformationalStderr(c);
    const e = new Error("boom");
    c.error("E1121 calculator_graph.cc:887] INTERNAL: failed");
    c.error(e);
    c.error("INFORMATION: not the runtime's prefix");
    expect(error.mock.calls).toEqual([["E1121 calculator_graph.cc:887] INTERNAL: failed"], [e], ["INFORMATION: not the runtime's prefix"]]);
    expect(info).not.toHaveBeenCalled();
  });
});
