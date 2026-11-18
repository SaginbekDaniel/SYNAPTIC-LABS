import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, LazyMotion, MotionConfig, domAnimation, m } from "motion/react";
import { SLIDES } from "./data/notes";
import { SLIDE_COUNT } from "./engine/deck";
import { useDeck } from "./engine/useDeck";
import { CANVAS_H, CANVAS_W, useFit } from "./engine/useFit";
import { Chrome } from "./ui/Chrome";
import { Help, Notes, Overview } from "./ui/Overlays";
import { Slide1 } from "./slides/Slide1";
import { Slide2 } from "./slides/Slide2";
import { Slide3 } from "./slides/Slide3";
import { Slide4 } from "./slides/Slide4";
import { Slide5 } from "./slides/Slide5";
import { Slide6 } from "./slides/Slide6";

const SLIDE_VIEWS = [Slide1, Slide2, Slide3, Slide4, Slide5, Slide6];
const isInteractive = (t: EventTarget | null) => t instanceof HTMLElement && !!t.closest("button, a, input, textarea, select, [role=button], [role=dialog]");

export function App() {
  const deck = useDeck();
  const { pos } = deck;
  const stage = useFit<HTMLDivElement>();

  const [overview, setOverview] = useState(false);
  const [help, setHelp] = useState(false);
  const [notes, setNotes] = useState(false);
  const [chromeOn, setChromeOn] = useState(true);
  const [fs, setFs] = useState(false);
  const [rotateDismissed, setRotateDismissed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const idle = useRef<number>();
  const modalOpen = overview || help;
  const fsSupported = typeof document !== "undefined" && !!document.fullscreenEnabled;

  const wake = useCallback(() => {
    setChromeOn(true);
    window.clearTimeout(idle.current);
    idle.current = window.setTimeout(() => setChromeOn(false), 3200);
  }, []);
  useEffect(() => {
    wake();
    return () => window.clearTimeout(idle.current);
  }, [wake]);

  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  useEffect(() => {
    const on = () => setFs(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!fsSupported) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen().catch(() => undefined);
  }, [fsSupported]);

  const restart = useCallback(() => {
    deck.restart();
    setElapsed(0);
    setRunning(false);
    setOverview(false);
  }, [deck]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      wake();
      if (modalOpen) return; // modals own the keyboard (Esc handled there)
      const activating = (e.key === " " || e.key === "Enter") && isInteractive(e.target);
      if (activating) return; // let buttons/links handle Space & Enter themselves
      let handled = true;
      switch (e.key) {
        case "ArrowRight": case "ArrowDown": case "PageDown": case " ":
          if (e.shiftKey && e.key === "ArrowRight") deck.nextSlide();
          else deck.next();
          break;
        case "ArrowLeft": case "ArrowUp": case "PageUp":
          if (e.shiftKey && e.key === "ArrowLeft") deck.prevSlide();
          else deck.prev();
          break;
        case "Home": deck.go({ slide: 0, step: 0 }); break;
        case "End": deck.go({ slide: SLIDE_COUNT - 1, step: 0 }); break;
        case "o": case "O": case "щ": case "Щ": setOverview(true); break;
        case "n": case "N": case "т": case "Т": setNotes((v) => !v); break;
        case "f": case "F": case "а": case "А": toggleFullscreen(); break;
        case "r": case "R": case "к": case "К": restart(); break;
        case "?": case "/": setHelp(true); break;
        case "Escape": if (notes) setNotes(false); break;
        default:
          if (/^[1-6]$/.test(e.key)) deck.go({ slide: Number(e.key) - 1, step: 0 });
          else handled = false;
      }
      if (handled) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [deck, modalOpen, notes, restart, toggleFullscreen, wake]);

  // touch swipe (touch only, so mouse text selection and hotspots are untouched)
  const swipe = useRef<{ x: number; y: number } | null>(null);
  const onPointerDown = (e: React.PointerEvent) => {
    wake();
    if (e.pointerType === "touch" && !isInteractive(e.target)) swipe.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const s = swipe.current;
    swipe.current = null;
    if (!s || e.pointerType !== "touch") return;
    const dx = e.clientX - s.x, dy = e.clientY - s.y;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) (dx < 0 ? deck.next : deck.prev)();
  };

  const View = SLIDE_VIEWS[pos.slide];
  const meta = SLIDES[pos.slide];
  const d = deck.direction.current;
  const portrait = stage.h > stage.w * 1.15;

  return (
    <LazyMotion features={domAnimation} strict>
    <MotionConfig reducedMotion="user">
      <h1 className="sr-only">NEXORA AI — интерактивная презентация</h1>
      <div className="app" onMouseMove={wake} onFocus={wake}>
        <div className="stage-area" ref={stage.ref} onPointerDown={onPointerDown} onPointerUp={onPointerUp} data-testid="stage">
          <div
            className="canvas"
            style={{ transform: `translate(${(-CANVAS_W * stage.scale) / 2}px, ${(-CANVAS_H * stage.scale) / 2}px) scale(${stage.scale})` }}
            data-testid="canvas"
          >
            <AnimatePresence initial={false} custom={d}>
              <m.div
                key={pos.slide}
                className="slide-layer"
                custom={d}
                variants={{
                  enter: (dir: number) => ({ opacity: 0, x: dir * 90, scale: 0.985 }),
                  center: { opacity: 1, x: 0, scale: 1 },
                  exit: (dir: number) => ({ opacity: 0, x: dir * -90, scale: 1.01 }),
                }}
                initial="enter" animate="center" exit="exit"
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                data-slide={pos.slide + 1}
              >
                <View step={pos.step} setStep={(n) => deck.go({ slide: pos.slide, step: n })} />
              </m.div>
            </AnimatePresence>
          </div>

          <Chrome
            pos={pos} visible={chromeOn || modalOpen} fullscreen={fs} fullscreenSupported={fsSupported} notesOpen={notes}
            onPrev={deck.prev} onNext={deck.next} onGoSlide={(i) => deck.go({ slide: i, step: 0 })}
            onOverview={() => setOverview(true)} onNotes={() => setNotes((v) => !v)} onFullscreen={toggleFullscreen}
            onRestart={restart} onHelp={() => setHelp(true)}
          />

          {portrait && !rotateDismissed && (
            <div className="rotate" role="status">
              <span>Презентация рассчитана на горизонтальный экран. Поверните устройство.</span>
              <button onClick={() => setRotateDismissed(true)}>Понятно</button>
            </div>
          )}
          {overview && <Overview pos={pos} onClose={() => setOverview(false)} onPick={(i) => { deck.go({ slide: i, step: 0 }); setOverview(false); }} onRestart={restart} />}
          {help && <Help onClose={() => setHelp(false)} />}
        </div>

        {notes && <Notes pos={pos} elapsed={elapsed} running={running} onToggle={() => setRunning((r) => !r)} onReset={() => { setElapsed(0); setRunning(false); }} onClose={() => setNotes(false)} />}
      </div>
      <div className="sr-only" aria-live="polite" data-testid="announce">
        Слайд {pos.slide + 1} из {SLIDE_COUNT}: {meta.headline}. Шаг {pos.step + 1} из {meta.notes.length}.
      </div>
    </MotionConfig>
    </LazyMotion>
  );
}
