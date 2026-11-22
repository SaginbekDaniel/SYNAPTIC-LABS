// Stand-in for the Nginx gateway, for running the Playwright suites against the PRODUCTION bundle with exactly
// the security headers docker/csp.mjs generates (no Docker needed): /vendor/ and /assets/ 404 when missing, SPA
// fallback otherwise, /api proxied. NOT the real gateway (no rate limits, no gateway token, no gzip): the real one
// is exercised by CI (docker compose smoke test). Usage: node gateway_sim.mjs <dist> <security-headers.conf> <port> <apiPort>
import { createServer, request } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
const [, , root, confPath, port, apiPort] = process.argv;
const headers = [...readFileSync(confPath, "utf8").matchAll(/add_header ([\w-]+) "([^"]*)" always;/g)].map((m) => [m[1], m[2]]);
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".woff2": "font/woff2", ".json": "application/json", ".svg": "image/svg+xml", ".task": "application/octet-stream", ".txt": "text/plain", ".webp": "image/webp", ".png": "image/png", ".ico": "image/x-icon" };
createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname.startsWith("/api/")) {
    const p = request({ host: "127.0.0.1", port: apiPort, path: req.url, method: req.method, headers: req.headers }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    req.pipe(p);
    return;
  }
  for (const [k, v] of headers) res.setHeader(k, v);
  let file = normalize(join(root, decodeURIComponent(url.pathname)));
  const isFile = file.startsWith(root) && existsSync(file) && statSync(file).isFile();
  if (!isFile) {
    if (url.pathname.startsWith("/vendor/") || url.pathname.startsWith("/assets/")) { res.writeHead(404); res.end(); return; }
    file = join(root, "index.html");
  }
  res.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream" });
  res.end(readFileSync(file));
}).listen(Number(port), "127.0.0.1");
