import { useSyncExternalStore } from "react";

/**
 * Colour theme. Dark is the art-directed default; the choice is a per-viewer convenience
 * kept in localStorage. index.html applies the same rule before first paint so there is no flash.
 */
export type ThemeChoice = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";

const KEY = "nexora.theme";
const listeners = new Set<() => void>();
const media = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: light)") : null;

function readChoice(): ThemeChoice {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "system" || v === "dark" ? v : "dark";
  } catch {
    return "dark";
  }
}

let choice: ThemeChoice = typeof window !== "undefined" ? readChoice() : "dark";
if (typeof document !== "undefined") syncThemeColor();

function resolve(c: ThemeChoice): ResolvedTheme {
  if (c === "system") return media?.matches ? "light" : "dark";
  return c;
}

/** Browser/PWA toolbar tint follows the active canvas token (the meta tag starts with the dark value). */
function syncThemeColor(): void {
  const canvas = getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim();
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta && canvas) meta.content = canvas;
}

function apply(): void {
  const resolved = resolve(choice);
  const root = document.documentElement;
  if (resolved === "light") root.dataset.theme = "light";
  else delete root.dataset.theme;
  syncThemeColor();
  listeners.forEach((l) => l());
}

media?.addEventListener("change", () => {
  if (choice === "system") apply();
});

export function setTheme(next: ThemeChoice): void {
  choice = next;
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    /* storage unavailable: the choice lasts for this page only */
  }
  apply();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useTheme(): { choice: ThemeChoice; resolved: ResolvedTheme } {
  const c = useSyncExternalStore(subscribe, () => choice);
  const resolved = useSyncExternalStore(subscribe, () => resolve(choice));
  return { choice: c, resolved };
}
