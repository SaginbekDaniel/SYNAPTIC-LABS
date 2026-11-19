// Zero-dependency static server for the pitch (Railway service `pitch`). Serves ./dist only.
// It exposes no API and proxies nothing: the deck is a public, synthetic-data-only static site.
import { createServer } from "node:http";
import { createReadStream, existsSync, statSync, readFileSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";
import { gzipSync } from "node:zlib";

const ROOT = resolve(process.env.PITCH_DIST ?? "dist");
const PORT = Number(process.env.PORT ?? 8080);

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png",
  ".woff2": "font/woff2", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8", ".map": "application/json",
};
const COMPRESSIBLE = new Set([".html", ".js", ".css", ".json", ".svg", ".txt"]);

const CSP = [
  "default-src 'self'", "script-src 'self'", "style-src 'self' 'unsafe-inline'", "img-src 'self' data:",
  "font-src 'self'", "connect-src 'self'", "object-src 'none'", "base-uri 'none'", "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

const SECURITY = {
  "Content-Security-Policy": CSP,
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Strict-Transport-Security": "max-age=31536000",
};

const gzCache = new Map();

function resolveFile(urlPath) {
  let p;
  try { p = decodeURIComponent(urlPath.split("?")[0]); } catch { return null; }
  const full = normalize(join(ROOT, p));
  if (full !== ROOT && !full.startsWith(ROOT + sep)) return null; // path traversal
  if (existsSync(full) && statSync(full).isFile()) return full;
  if (existsSync(full) && statSync(full).isDirectory() && existsSync(join(full, "index.html"))) return join(full, "index.html");
  if (!extname(p)) return join(ROOT, "index.html"); // SPA-style fallback for extension-less paths
  return undefined;
}

export const server = createServer((req, res) => {
  const send = (code, body, extra = {}) => { res.writeHead(code, { ...SECURITY, "Content-Type": "text/plain; charset=utf-8", ...extra }); res.end(body); };
  if (req.method !== "GET" && req.method !== "HEAD") return send(405, "Method Not Allowed", { Allow: "GET, HEAD" });
  const url = req.url ?? "/";
  if (url === "/healthz") return send(200, "ok", { "Cache-Control": "no-store" });

  const file = resolveFile(url);
  if (file === null) return send(400, "Bad Request");
  if (file === undefined || !existsSync(file)) return send(404, "Not Found");

  const ext = extname(file);
  const hashed = file.includes(`${sep}assets${sep}`);
  const headers = {
    ...SECURITY,
    "Content-Type": TYPES[ext] ?? "application/octet-stream",
    "Cache-Control": hashed ? "public, max-age=31536000, immutable" : ext === ".html" ? "no-cache" : "public, max-age=3600",
    Vary: "Accept-Encoding",
  };
  const wantsGzip = COMPRESSIBLE.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] ?? "");
  if (wantsGzip) {
    let buf = gzCache.get(file);
    if (!buf) { buf = gzipSync(readFileSync(file)); gzCache.set(file, buf); }
    res.writeHead(200, { ...headers, "Content-Encoding": "gzip", "Content-Length": buf.length });
    return res.end(req.method === "HEAD" ? undefined : buf);
  }
  res.writeHead(200, { ...headers, "Content-Length": statSync(file).size });
  if (req.method === "HEAD") return res.end();
  createReadStream(file).pipe(res);
});

if (import.meta.url === `file://${process.argv[1]}`) {
  server.listen(PORT, "0.0.0.0", () => console.log(`nexora-pitch listening on :${PORT}, serving ${ROOT}`));
  const stop = () => server.close(() => process.exit(0));
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
