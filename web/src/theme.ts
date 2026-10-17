import { useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

// index.html applies the stored choice before the page paints; keep the key in step with it.
const KEY = "arcsong.theme";
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

function stored(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

let theme: Theme = stored();

export function setTheme(next: Theme) {
  theme = next;
  try {
    if (next === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, next);
  } catch {
    // Private windows may refuse storage; the choice still holds until the page reloads.
  }
  if (next === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = next;
  listeners.forEach((listener) => listener());
}

dark.addEventListener("change", () => listeners.forEach((listener) => listener()));

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The user's choice: System follows macOS. */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, () => theme);
}

/** What is showing, for anything that reads colours once, like a canvas waveform. */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, () => (theme === "system" ? (dark.matches ? "dark" : "light") : theme));
}

export const THEMES: { value: Theme; label: string; icon: string }[] = [
  { value: "system", label: "Match the system", icon: "◐" },
  { value: "light", label: "Light", icon: "☀" },
  { value: "dark", label: "Dark", icon: "☾" },
];
