import type { Setup } from "./api";

/** Where new songs render, when the server offers more than one Engine (this Mac, Modal, RunPod). */
const KEY = "arcsong.engine";

export const ENGINE_LABELS: Record<string, string> = { mlx: "This Mac", modal: "Modal", runpod: "RunPod" };

export function storedEngine(): string | undefined {
  try {
    return localStorage.getItem(KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function storeEngine(id: string | undefined): void {
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    // Private windows can refuse storage; the server's default Engine is used then.
  }
}

/** The Engine new songs go to: the stored choice while it is set up, else the server's default.
 * Undefined when there is only one Engine. */
export function chosenEngine(setup: Setup | null): string | undefined {
  if (!setup || setup.engines.length < 2) return undefined;
  const stored = storedEngine();
  return setup.engines.find((e) => e.id === stored && e.usable)?.id ?? setup.default_engine;
}

/** Forget a stored choice that is no longer set up, so requests fall back to the default. */
export function reconcileEngine(setup: Setup | null): void {
  if (!setup) return;
  const stored = storedEngine();
  if (stored && !setup.engines.some((e) => e.id === stored && e.usable)) storeEngine(undefined);
}
