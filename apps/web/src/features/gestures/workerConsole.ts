/**
 * MediaPipe's WASM loader (Emscripten) binds the runtime's stderr to `console.error` when it loads,
 * so purely informational TensorFlow Lite lines — e.g. "INFO: Created TensorFlow Lite XNNPACK
 * delegate for CPU." on every healthy start — show up as errors in the developer console.
 *
 * Installed in the landmark worker before MediaPipe is imported: lines that declare themselves
 * informational ("INFO: …") go to `console.info`; everything else still reaches `console.error`.
 */
export function routeInformationalStderr(target: Pick<Console, "error" | "info">): void {
  const error = target.error.bind(target);
  const info = target.info.bind(target);
  target.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].startsWith("INFO: ")) info(...args);
    else error(...args);
  };
}
