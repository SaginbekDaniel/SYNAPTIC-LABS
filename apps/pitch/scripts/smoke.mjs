// Usage: node scripts/smoke.mjs https://host   — verifies a deployed pitch over real HTTP(S).
const base = (process.argv[2] ?? "").replace(/\/$/, "");
if (!base) { console.error("usage: smoke.mjs <base-url>"); process.exit(2); }
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); if (!ok) failed++; };

const home = await fetch(base + "/");
const html = await home.text();
check("GET / → 200 html", home.status === 200 && /text\/html/.test(home.headers.get("content-type") ?? ""), `(${home.status})`);
check("title present", /<title>NEXORA/.test(html));
check("CSP header", /default-src 'self'/.test(home.headers.get("content-security-policy") ?? ""));
check("nosniff header", home.headers.get("x-content-type-options") === "nosniff");

const assets = [...html.matchAll(/(?:src|href)="(\.?\/?assets\/[^"]+)"/g)].map((m) => m[1].replace(/^\.\//, "/").replace(/^(?!\/)/, "/"));
check("has hashed assets", assets.length >= 2, `(${assets.length})`);
for (const a of assets) {
  const r = await fetch(base + a);
  check(`asset ${a}`, r.status === 200 && (r.headers.get("cache-control") ?? "").includes("immutable"), `(${r.status})`);
}
for (const s of ["queue", "investigation"]) {
  const r = await fetch(`${base}/shots/${s}.webp`);
  check(`screenshot ${s}.webp`, r.status === 200 && /image\/webp/.test(r.headers.get("content-type") ?? ""), `(${r.status})`);
}
const hz = await fetch(base + "/healthz");
check("/healthz → 200", hz.status === 200);
const miss = await fetch(base + "/nope.js");
check("missing asset → 404", miss.status === 404);
const post = await fetch(base + "/", { method: "POST" });
check("POST rejected", post.status === 405);
const api = await fetch(base + "/api/v1/datasets");
const apiText = await api.text();
check("no API exposed on this host", !/"items"|datasets|detail/.test(apiText) || /<title>NEXORA/.test(apiText), `(${api.status})`);
console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
process.exit(failed ? 1 : 0);
