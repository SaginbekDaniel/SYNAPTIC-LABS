# Camera gestures — manual verification on real hardware

**Status: NOT YET EXECUTED.** No run on a physical webcam has been recorded. CI and the automated
suite (`apps/web/e2e/gestures.spec.ts`) use Chromium's synthetic camera, which shows no hand, plus a
scripted landmark worker; they prove lifecycle, consent, privacy and wiring — not recognition
quality on real hands. Record each run in the table at the end; do not mark a row passed without
having performed it.

## Setup

1. Production-like build (the dev server is acceptable for a first pass, but the gateway CSP only
   applies to the built image):
   `docker compose up --build -d --wait`, create an analyst
   (`docker compose run --rm api python -m nexora.auth.cli create-user analyst --generate`), sign in
   at http://127.0.0.1:8080 (camera access requires a secure context: `localhost`/`127.0.0.1` or HTTPS).
2. **Лаборатория** → generate `demo-v1` → *Запустить анализ* → **Граф связей**.
3. Open DevTools → Network (preserve log) and Console before enabling the camera.

## Checklist

| # | Step | Expected |
|---|---|---|
| 1 | Click the camera icon in the graph toolbar | Consent dialog explains local-only processing; **no** browser permission prompt yet |
| 2 | *Отмена* | Dialog closes; no camera prompt; camera LED off |
| 3 | Camera icon → *Включить камеру* → deny in the browser | "Загрузка модели…" first (camera LED **off**, no prompt yet), then the browser prompt; after denying: "Доступ к камере запрещён…"; mouse/keyboard graph control unaffected |
| 4 | Reset permission, enable again, allow | "Загрузка модели…" with the camera LED **off** and the button reading *Отменить включение*; then the prompt, "Запрос доступа к камере…", "Покажите руку в кадре", *Камера включена* and the preview. On a throttled network (DevTools "Slow 4G") the LED stays off for the whole download |
| 5 | Network tab | Only same-origin requests: `/vendor/mediapipe/vision_wasm_module_internal.{js,wasm}`, `hand_landmarker.task`. **No** request to `*.googleapis.com` or any other origin at any time, including after stopping |
| 6 | Show an open palm (dominant hand) for ~0.5 s | Status "Рука в кадре"; pointer appears over the graph |
| 7 | Open palm and move | Graph pans ("сдвиг"); stops when the hand stops |
| 8 | Point with the index finger over a node | Node hover highlight follows the pointer |
| 9 | Short pinch over a node | Node selected; account summary opens. In *Навигация* mode the node does **not** move |
| 10 | Switch to *Расстановка*; pinch, move, release over a node | Node is dragged and dropped; layout elsewhere unchanged |
| 11 | Two-hand pinch, move hands apart / together | Zoom in / out around the hands' midpoint |
| 12 | Make a fist, wave, partially leave the frame | No selection, drag or zoom is triggered (fist must not read as a pinch) |
| 13 | Remove the hand mid-drag | "Рука не видна — жест отменён"; the drag is cancelled and the node returns to exactly where it started |
| 14 | Switch *Ведущая рука* to *Левая* and repeat 6–9 with the left hand | Same behaviour |
| 15 | Press Esc | Camera off (LED off), panel closes, `aria-pressed=false` |
| 16 | Enable again, switch to another browser tab, come back | Camera turned off while hidden; message explains it; **not** restarted automatically |
| 17 | Enable again, navigate to **Проверки** | Camera off (LED off) |
| 18 | Low light / backlight / glasses / sleeves | Note recognition quality; no spurious actions |
| 19 | Performance: DevTools Performance, 30 s with a hand in view | Main thread stays responsive (inference runs in the worker, ≤ 30 frames/s); note CPU % |
| 20 | Console during the whole run | No errors (MediaPipe's informational "INFO:" lines are routed to `console.info`) |

## Results log

| Date | Build / commit | Browser + OS | Camera | Steps passed | Notes / defects |
|---|---|---|---|---|---|
| — | — | — | — | — | not yet executed |
