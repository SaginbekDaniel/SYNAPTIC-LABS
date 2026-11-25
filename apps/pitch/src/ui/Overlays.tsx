import { type ReactNode, useEffect, useRef } from "react";
import { SLIDES, TARGET_SECONDS } from "../data/notes";
import { SLIDE_COUNT, STEP_COUNTS, type Pos } from "../engine/deck";
import { Icon } from "./primitives";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** Modal with focus trap, Escape to close and focus restore. */
function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("[data-autofocus], button");
    first?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
      if (e.key !== "Tab" || !ref.current) return;
      const f = [...ref.current.querySelectorAll<HTMLElement>("button, a[href]")].filter((el) => !el.hasAttribute("disabled"));
      if (!f.length) return;
      const a = f[0], z = f[f.length - 1];
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    };
    window.addEventListener("keydown", trap, true);
    return () => {
      window.removeEventListener("keydown", trap, true);
      prevFocus?.focus?.();
    };
  }, [onClose]);
  return (
    <div className="modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="close" onClick={onClose} aria-label="Закрыть (Esc)"><Icon name="close" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Overview({ pos, onPick, onClose, onRestart }: { pos: Pos; onPick: (i: number) => void; onClose: () => void; onRestart: () => void }) {
  return (
    <Modal title="Обзор слайдов" onClose={onClose} wide>
      <ol className="ov-grid">
        {SLIDES.map((s, i) => (
          <li key={s.id}>
            <button className={`ov-card ${i === pos.slide ? "current" : ""}`} data-autofocus={i === pos.slide ? "" : undefined} onClick={() => onPick(i)} aria-current={i === pos.slide ? "true" : undefined}>
              <span className="ov-n mono">{String(i + 1).padStart(2, "0")}</span>
              <span className="ov-eyebrow">{s.eyebrow}</span>
              <span className="ov-title">{s.headline}</span>
              <span className="ov-meta">{STEP_COUNTS[i]} {STEP_COUNTS[i] === 1 ? "шаг" : STEP_COUNTS[i] < 5 ? "шага" : "шагов"} · ~{s.seconds} с</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="modal-foot">
        <button className="btn" onClick={onRestart}><Icon name="restart" /> Начать заново</button>
        <span className="small">Клавиши 1–{SLIDE_COUNT} — переход к слайду. Всего ≈ {fmt(TARGET_SECONDS)}.</span>
      </div>
    </Modal>
  );
}

const KEYS: [string, string][] = [
  ["→  ↓  Пробел  PgDn", "Следующий шаг"],
  ["←  ↑  PgUp", "Предыдущий шаг"],
  ["Shift + →  /  Shift + ←", "Следующий / предыдущий слайд"],
  [`1 – ${SLIDE_COUNT}`, "Перейти к слайду"],
  ["Home  /  End", "Первый / последний слайд"],
  ["O", "Обзор слайдов"],
  ["N", "Заметки докладчика"],
  ["F", "Полный экран"],
  ["R", "Начать заново"],
  ["?", "Эта подсказка"],
  ["Esc", "Закрыть окно"],
];
export function Help({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Горячие клавиши" onClose={onClose}>
      <dl className="keys">
        {KEYS.map(([k, d]) => (
          <div key={k}><dt className="mono">{k}</dt><dd>{d}</dd></div>
        ))}
        <div><dt className="mono">Свайп</dt><dd>Влево / вправо — шаг вперёд / назад</dd></div>
      </dl>
    </Modal>
  );
}

export function Notes({ pos, elapsed, running, onToggle, onReset, onClose }: { pos: Pos; elapsed: number; running: boolean; onToggle: () => void; onReset: () => void; onClose: () => void }) {
  const s = SLIDES[pos.slide];
  const budgetBefore = SLIDES.slice(0, pos.slide).reduce((a, x) => a + x.seconds, 0);
  const planned = budgetBefore + s.seconds * ((pos.step + 1) / s.notes.length);
  const delta = Math.round(elapsed - planned);
  const nextS = SLIDES[pos.slide + 1];
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    list.current?.querySelector("li.on")?.scrollIntoView({ block: "nearest" });
  }, [pos.slide, pos.step]);
  return (
    <aside className="notes" aria-label="Заметки докладчика">
      <header>
        <h2>Заметки докладчика</h2>
        <button className="close" onClick={onClose} aria-label="Закрыть заметки (N)"><Icon name="close" /></button>
      </header>
      <div className="timer">
        <div>
          <div className="t mono" aria-label={`Прошло ${fmt(elapsed)} из ${fmt(TARGET_SECONDS)}`}>{fmt(elapsed)}<small> / {fmt(TARGET_SECONDS)}</small></div>
          <div className={`pace ${delta > 8 ? "late" : delta < -8 ? "early" : ""}`}>
            {!running && elapsed === 0 ? "Таймер не запущен" : delta > 8 ? `Отстаёте на ${delta} с` : delta < -8 ? `Опережаете на ${-delta} с` : "В графике"}
          </div>
        </div>
        <div className="timer-btns">
          <button onClick={onToggle} aria-label={running ? "Пауза таймера" : "Запустить таймер"}><Icon name={running ? "pause" : "play"} /></button>
          <button onClick={onReset} aria-label="Сбросить таймер"><Icon name="restart" /></button>
        </div>
      </div>
      <div className="n-slide">Слайд {pos.slide + 1} · {s.title} · бюджет {s.seconds} с</div>
      <ol className="n-list" ref={list}>
        {s.notes.map((n, i) => (
          <li key={i} className={i === pos.step ? "on" : i < pos.step ? "done" : ""} aria-current={i === pos.step ? "step" : undefined}>
            <span className="mono">{i + 1}</span>
            <p>{n}</p>
          </li>
        ))}
      </ol>
      {nextS && <div className="n-next"><span className="label">Далее</span><b>{nextS.headline}</b></div>}
    </aside>
  );
}
