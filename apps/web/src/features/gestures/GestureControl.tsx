import { useEffect, useId, useMemo, useRef, useSyncExternalStore } from "react";
import type { GraphController } from "../../components/graph/controller";
import { Icon, Segmented } from "../../components/ui";
import { t, type MessageKey } from "../../lib/i18n";
import { useMediaQuery } from "../../lib/useMediaQuery";
import type { GestureMode } from "./adapter";
import { GestureSession, type GestureSnapshot, type GestureUi } from "./gestureSession";

/** Create the session for a graph stage and tie its lifetime to the component and the tab. */
export function useGestureSession(controller: GraphController | null): GestureSession {
  const session = useMemo(() => new GestureSession(), []);
  useEffect(() => session.setController(controller), [session, controller]);
  useEffect(() => {
    // A hidden tab stops the camera outright; coming back requires a new, deliberate start.
    const onVisibility = () => {
      if (document.visibilityState === "hidden" && session.active) session.stop("hidden");
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && session.active) session.stop();
    };
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("keydown", onKey);
      // Route change, sign-out or unmount: release camera and worker.
      session.stop();
    };
  }, [session]);
  return session;
}

function useSlice<T>(session: GestureSession, pick: (s: GestureSnapshot) => T): T {
  return useSyncExternalStore(session.subscribe, () => pick(session.getSnapshot()));
}

/** Gestures need a precise pointer context and a camera; phones keep the touch interface. */
export function useGesturesSupported(): boolean {
  const fine = useMediaQuery("(any-pointer: fine)");
  return fine && typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof Worker !== "undefined";
}

/** The camera is on only from calibration onwards: the model loads first, then the camera is requested. */
function cameraLive(ui: GestureUi): boolean {
  return ui === "calibrating" || ui === "active";
}

export function GestureToggle({ session }: { session: GestureSession }) {
  const ui = useSlice(session, (s) => s.ui);
  const supported = useGesturesSupported();
  if (!supported) return null;
  const on = ui === "starting" || ui === "loading" || ui === "calibrating" || ui === "active";
  const label = cameraLive(ui) ? t("gesture.stop") : on ? t("gesture.cancel") : t("gesture.enable");
  return (
    <>
      <span className="graph-stage__sep" aria-hidden="true" />
      <button
        type="button"
        className={`icon-btn${on ? " icon-btn--live" : ""}`}
        aria-pressed={on}
        aria-label={label}
        title={label}
        data-testid="gesture-toggle"
        onClick={() => (on ? session.stop() : session.requestConsent())}
      >
        <Icon name={on ? "cameraOff" : "camera"} />
      </button>
    </>
  );
}

const STATUS: Record<string, MessageKey> = {
  starting: "gesture.status.starting",
  loading: "gesture.status.loading",
  calibrating: "gesture.status.calibrating",
  tracked: "gesture.status.tracked",
  searching: "gesture.status.searching",
  lost: "gesture.status.lost",
};
const FAILURE: Record<string, MessageKey> = {
  denied: "gesture.fail.denied",
  unavailable: "gesture.fail.unavailable",
  in_use: "gesture.fail.inUse",
  insecure: "gesture.fail.insecure",
  ended: "gesture.fail.ended",
  error: "gesture.fail.error",
  engine: "gesture.fail.engine",
  hidden: "gesture.fail.hidden",
};
const PHASE: Partial<Record<GestureSnapshot["phase"], MessageKey>> = {
  hover: "gesture.phase.hover",
  panning: "gesture.phase.panning",
  pinching: "gesture.phase.pinching",
  dragging: "gesture.phase.dragging",
  zooming: "gesture.phase.zooming",
};

export function GestureLayer({ session }: { session: GestureSession }) {
  const ui = useSlice(session, (s) => s.ui);
  const failure = useSlice(session, (s) => s.failure);
  const tracking = useSlice(session, (s) => s.tracking);
  const phase = useSlice(session, (s) => s.phase);
  const mode = useSlice(session, (s) => s.mode);
  const dominant = useSlice(session, (s) => s.dominant);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    session.attachVideo(videoRef.current);
    return () => session.attachVideo(null);
  }, [session]);

  const on = ui === "starting" || ui === "loading" || ui === "calibrating" || ui === "active";
  const live = cameraLive(ui);
  const status: MessageKey | null =
    (ui === "failed" && failure ? FAILURE[failure] : ui === "active" ? STATUS[tracking] : ui === "starting" || ui === "loading" || ui === "calibrating" ? STATUS[ui] : null) ?? null;

  return (
    <>
      {/* Always mounted so a start can attach the stream; shown only while the camera is on. */}
      <div className={`gesture-panel${on || ui === "failed" ? "" : " gesture-panel--hidden"}`} role="region" aria-labelledby={titleId} data-testid="gesture-panel">
        <div className="gesture-panel__head">
          <span id={titleId} className="gesture-panel__title">
            <Icon name="camera" size={16} />
            {t("gesture.title")}
          </span>
          {live && <span className="gesture-panel__live">{t("gesture.cameraOn")}</span>}
        </div>
        <video ref={videoRef} className={`gesture-panel__video${live ? "" : " visually-hidden"}`} muted playsInline aria-label={t("gesture.preview")} />
        <p className={`gesture-panel__status gesture-panel__status--${ui === "failed" ? "failed" : tracking}`} role="status" aria-live="polite" data-testid="gesture-status">
          {status ? t(status) : ""}
          {ui === "active" && tracking === "tracked" && PHASE[phase] ? ` · ${t(PHASE[phase]!)}` : ""}
        </p>
        {on && (
          <>
            <Segmented<GestureMode>
              size="sm"
              label={t("gesture.mode")}
              value={mode}
              options={[
                { value: "navigate", label: t("gesture.mode.navigate") },
                { value: "arrange", label: t("gesture.mode.arrange") },
              ]}
              onChange={(m) => session.setMode(m)}
            />
            <label className="gesture-panel__hand">
              {t("gesture.hand")}
              <select className="select select--sm" value={dominant} onChange={(e) => session.setDominant(e.target.value === "Left" ? "Left" : "Right")}>
                <option value="Right">{t("gesture.hand.right")}</option>
                <option value="Left">{t("gesture.hand.left")}</option>
              </select>
            </label>
            <details className="gesture-panel__help">
              <summary>{t("gesture.help")}</summary>
              <ul>
                <li>{t("gesture.help.open")}</li>
                <li>{t("gesture.help.point")}</li>
                <li>{t("gesture.help.pinch")}</li>
                <li>{t("gesture.help.drag")}</li>
                <li>{t("gesture.help.zoom")}</li>
                <li>{t("gesture.help.stop")}</li>
              </ul>
            </details>
          </>
        )}
        <div className="gesture-panel__actions">
          {on ? (
            <button type="button" className="btn btn--sm" onClick={() => session.stop()} data-testid="gesture-stop">
              <Icon name="cameraOff" size={16} />
              {live ? t("gesture.stop") : t("gesture.cancel")}
            </button>
          ) : (
            <button type="button" className="btn btn--sm" onClick={() => session.stop()}>
              {t("common.close")}
            </button>
          )}
        </div>
      </div>
      {ui === "consent" && <ConsentDialog session={session} />}
      {ui === "active" && <GesturePointer session={session} />}
    </>
  );
}

function ConsentDialog({ session }: { session: GestureSession }) {
  const titleId = useId();
  const ref = useRef<HTMLButtonElement | null>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div className="gesture-consent" role="dialog" aria-modal="false" aria-labelledby={titleId} data-testid="gesture-consent">
      <h3 id={titleId}>{t("gesture.consent.title")}</h3>
      <ul>
        <li>{t("gesture.consent.local")}</li>
        <li>{t("gesture.consent.noStore")}</li>
        <li>{t("gesture.consent.readOnly")}</li>
        <li>{t("gesture.consent.stop")}</li>
      </ul>
      <div className="gesture-consent__actions">
        <button ref={ref} type="button" className="btn btn--primary btn--sm" onClick={() => void session.start()} data-testid="gesture-start">
          <Icon name="camera" size={16} />
          {t("gesture.consent.start")}
        </button>
        <button type="button" className="btn btn--sm" onClick={() => session.dismissConsent()}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

function GesturePointer({ session }: { session: GestureSession }) {
  const pointer = useSlice(session, (s) => s.pointer);
  if (!pointer) return null;
  return (
    <span
      className={`gesture-pointer gesture-pointer--${pointer.pose}${pointer.target ? " gesture-pointer--target" : ""}`}
      style={{ left: `${pointer.x * 100}%`, top: `${pointer.y * 100}%` }}
      aria-hidden="true"
      data-testid="gesture-pointer"
    />
  );
}
