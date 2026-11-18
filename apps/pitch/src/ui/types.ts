export interface SlideProps {
  /** current reveal state of this slide */
  step: number;
  /** jump to a reveal state of this slide (used by in-slide controls) */
  setStep: (n: number) => void;
}
