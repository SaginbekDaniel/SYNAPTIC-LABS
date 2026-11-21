// Self-hosted, hash-pinned assets for the optional camera-gesture mode.
//
// The browser never loads MediaPipe code or models from a CDN: this step places them under
// public/vendor/mediapipe/ (git-ignored), and every file must match the SHA-256 pinned below.
//  * WASM loader + binary: copied from node_modules/@mediapipe/tasks-vision (version pinned
//    exactly in package.json, integrity pinned in package-lock.json).
//  * hand_landmarker.task: Google's published Hand Landmarker model (float16, v1, Apache-2.0),
//    downloaded once at build time and verified here.
//
// Production builds fail closed on any mismatch. The dev server only warns, so the rest of the
// app stays usable offline; the gesture mode then reports that its model could not load.
import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const out = join(web, "public", "vendor", "mediapipe");
const pkg = join(web, "node_modules", "@mediapipe", "tasks-vision");

export const MEDIAPIPE_VERSION = "1.2.2";
export const ASSETS = [
  {
    name: "vision_wasm_module_internal.js",
    from: join(pkg, "wasm", "vision_wasm_module_internal.js"),
    sha256: "72fba0ac8a4034ce9d63f68389df1dead52069409ea621688eedf97f01d4362f",
  },
  {
    name: "vision_wasm_module_internal.wasm",
    from: join(pkg, "wasm", "vision_wasm_module_internal.wasm"),
    sha256: "b8927a2eebfe80dd98a426a210a9e820c8215168c06f3bcf5d4d09080f623db5",
  },
  {
    name: "hand_landmarker.task",
    url: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    sha256: "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1",
  },
];

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

async function existingMatches(path, expected) {
  try {
    return sha256(await readFile(path)) === expected;
  } catch {
    return false;
  }
}

export async function ensureGestureAssets({ strict = true, log = console } = {}) {
  await mkdir(out, { recursive: true });
  const installed = JSON.parse(await readFile(join(pkg, "package.json"), "utf8")).version;
  if (installed !== MEDIAPIPE_VERSION) {
    throw new Error(`@mediapipe/tasks-vision ${installed} installed, ${MEDIAPIPE_VERSION} pinned: update scripts/gesture-assets.mjs hashes deliberately`);
  }
  for (const a of ASSETS) {
    const target = join(out, a.name);
    if (await existingMatches(target, a.sha256)) continue;
    try {
      let data;
      if (a.from) {
        data = await readFile(a.from);
      } else {
        const res = await fetch(a.url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        data = Buffer.from(await res.arrayBuffer());
      }
      const actual = sha256(data);
      if (actual !== a.sha256) throw new Error(`sha256 mismatch: expected ${a.sha256}, got ${actual}`);
      await writeFile(`${target}.part`, data);
      await rename(`${target}.part`, target);
      log.info?.(`gesture assets: ${a.name} verified`);
    } catch (err) {
      const msg = `gesture assets: ${a.name}: ${err instanceof Error ? err.message : String(err)}`;
      if (strict) throw new Error(msg);
      log.warn?.(`${msg} — camera gestures will report that the model is unavailable`);
    }
  }
  // Provenance note served next to the files (no secrets, no user data).
  await writeFile(
    join(out, "PROVENANCE.txt"),
    [
      `@mediapipe/tasks-vision ${MEDIAPIPE_VERSION} (Apache-2.0) — WASM copied from the npm package`,
      `hand_landmarker.task float16 v1 (Apache-2.0) — ${ASSETS[2].url}`,
      ...ASSETS.map((a) => `${a.sha256}  ${a.name}`),
      "",
    ].join("\n"),
  );
}

/** Vite plugin: assets are ready before the dev server or the production build starts. */
export function gestureAssets() {
  let strict = true;
  return {
    name: "nexora-gesture-assets",
    configResolved(config) {
      strict = config.command === "build";
    },
    async buildStart() {
      await ensureGestureAssets({ strict, log: { info: () => {}, warn: (m) => this.warn(m) } });
    },
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await ensureGestureAssets({ strict: true });
}
