import { SLIDES } from "../data/notes";
import { STEP_COUNTS, type Pos } from "../engine/deck";
import { Icon } from "./primitives";

interface Props {
  pos: Pos;
  visible: boolean;
  fullscreen: boolean;
  fullscreenSupported: boolean;
  notesOpen: boolean;
  onPrev: () => void;
  onNext: () => void;
  onGoSlide: (i: number) => void;
  onOverview: () => void;
  onNotes: () => void;
  onFullscreen: () => void;
  onRestart: () => void;
  onHelp: () => void;
}

/**
 * Presentation chrome. It lives in the bottom margin of the viewport (inside the canvas's 80px safe area
 * at 16:9), so it never covers slide content. The toolbar fades out when idle; progress stays.
 */
export function Chrome(p: Props) {
  const atStart = p.pos.slide === 0 && p.pos.step === 0;
  const atEnd = p.pos.slide === STEP_COUNTS.length - 1;
  return (
    <div className={`chrome ${p.visible ? "show" : ""}`}>
      <nav className="progress" aria-label="Прогресс презентации">
        {SLIDES.map((s, i) => {
          const fill = i < p.pos.slide ? 1 : i === p.pos.slide ? (p.pos.step + 1) / STEP_COUNTS[i] : 0;
          return (
            <button key={s.id} className="seg-bar" aria-label={`Слайд ${i + 1}: ${s.title}`} aria-current={i === p.pos.slide ? "step" : undefined} onClick={() => p.onGoSlide(i)}>
              <><span /><i style={{ transform: `scaleX(${fill})` }} /></>
            </button>
          );
        })}
        <span className="counter mono" aria-hidden="true">{String(p.pos.slide + 1).padStart(2, "0")} / {String(SLIDES.length).padStart(2, "0")}</span>
      </nav>
      <div className="toolbar" role="toolbar" aria-label="Управление презентацией">
        <button onClick={p.onPrev} disabled={atStart} aria-label="Назад (←)" title="Назад (←)"><Icon name="prev" /></button>
        <button onClick={p.onNext} disabled={atEnd} aria-label="Далее (→ или Пробел)" title="Далее (→ или Пробел)"><Icon name="next" /></button>
        <span className="sep" />
        <button onClick={p.onOverview} aria-label="Обзор слайдов (O)" title="Обзор слайдов (O)"><Icon name="grid" /></button>
        <button onClick={p.onNotes} aria-pressed={p.notesOpen} aria-label="Заметки докладчика (N)" title="Заметки докладчика (N)"><Icon name="notes" /></button>
        <button onClick={p.onFullscreen} disabled={!p.fullscreenSupported} aria-pressed={p.fullscreen} aria-label={p.fullscreen ? "Выйти из полноэкранного режима (F)" : "Полный экран (F)"} title={p.fullscreenSupported ? "Полный экран (F)" : "Полный экран недоступен в этом браузере"}><Icon name={p.fullscreen ? "exit" : "full"} /></button>
        <button onClick={p.onRestart} aria-label="Начать заново (R)" title="Начать заново (R)"><Icon name="restart" /></button>
        <button onClick={p.onHelp} aria-label="Горячие клавиши (?)" title="Горячие клавиши (?)"><Icon name="help" /></button>
      </div>
    </div>
  );
}
