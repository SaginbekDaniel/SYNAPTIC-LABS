// Emit the gateway's security-header snippet for a built index.html.
// The Content-Security-Policy allows exactly the inline scripts present in the build (by SHA-256),
// so the pre-paint theme script keeps working without 'unsafe-inline'.
// Usage: node docker/csp.mjs dist/index.html > security-headers.conf
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2] ?? "dist/index.html", "utf8");
const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
  .map((m) => m[1])
  .filter((body) => body.trim().length > 0)
  .map((body) => `'sha256-${createHash("sha256").update(body, "utf8").digest("base64")}'`);

const csp = [
  "default-src 'self'",
  `script-src 'self' ${hashes.join(" ")}`.trim(),
  // React and Cytoscape set inline style attributes.
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

process.stdout.write(
  [
    "# Generated at image build by docker/csp.mjs — do not edit.",
    `add_header Content-Security-Policy "${csp}" always;`,
    'add_header X-Content-Type-Options "nosniff" always;',
    'add_header X-Frame-Options "DENY" always;',
    'add_header Referrer-Policy "same-origin" always;',
    'add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;',
    'add_header Cross-Origin-Opener-Policy "same-origin" always;',
    'add_header Cross-Origin-Resource-Policy "same-origin" always;',
    // Only meaningful over HTTPS; $nexora_hsts is empty for plain-HTTP local requests.
    'add_header Strict-Transport-Security $nexora_hsts always;',
    "",
  ].join("\n"),
);
