import { useSyncExternalStore } from "react";
import { api, type Peaks } from "./api";

/** What the player bar shows for the song it plays. */
export interface Track {
  songId: number;
  title: string;
  subtitle: string;
  seconds: number | null;
}

interface State {
  track: Track | null;
  playing: boolean;
  duration: number | null;
  error: string | null;
}

/** One audio element for the whole page, so a song keeps playing from view to view. */
const audio = new Audio();
audio.preload = "auto";

let state: State = { track: null, playing: false, duration: null, error: null };
const listeners = new Set<() => void>();
const positionListeners = new Set<() => void>();

function set(patch: Partial<State>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

function notifyPosition() {
  positionListeners.forEach((listener) => listener());
}

audio.addEventListener("play", () => set({ playing: true }));
audio.addEventListener("pause", () => set({ playing: false }));
audio.addEventListener("ended", () => set({ playing: false }));
audio.addEventListener("loadedmetadata", () => set({ duration: audio.duration }));
audio.addEventListener("timeupdate", notifyPosition);
audio.addEventListener("seeked", notifyPosition);
audio.addEventListener("error", () => {
  if (state.track) set({ error: "This song could not be played.", playing: false });
});

// Only one thing sounds at a time: the bar, a Compare Take or the Score's melody preview.
// Whoever starts claims the audio and everyone else stops.
const CLAIM = "arcsong:audio";

export function claimAudio(owner: string) {
  window.dispatchEvent(new CustomEvent(CLAIM, { detail: owner }));
}

export function onAudioClaimed(owner: string, stop: () => void): () => void {
  const handler = (event: Event) => {
    if ((event as CustomEvent<string>).detail !== owner) stop();
  };
  window.addEventListener(CLAIM, handler);
  return () => window.removeEventListener(CLAIM, handler);
}

onAudioClaimed("player", () => audio.pause());

function updateMediaSession(track: Track) {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({ title: track.title, artist: "Arcsong", album: track.subtitle });
}

if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => player.toggle());
  navigator.mediaSession.setActionHandler("pause", () => player.pause());
  navigator.mediaSession.setActionHandler("seekbackward", () => player.seek(audio.currentTime - 10));
  navigator.mediaSession.setActionHandler("seekforward", () => player.seek(audio.currentTime + 10));
  navigator.mediaSession.setActionHandler("seekto", (details) => {
    if (details.seekTime !== undefined) player.seek(details.seekTime);
  });
}

export const player = {
  /** Play `track`, from `at` seconds if given, else from where it was. */
  play(track: Track, at?: number) {
    claimAudio("player");
    if (state.track?.songId !== track.songId) {
      audio.src = api.audioUrl(track.songId);
      set({ track, duration: track.seconds, error: null });
      updateMediaSession(track);
    } else if (state.track.title !== track.title) {
      player.rename(track.songId, track.title);
    }
    if (at !== undefined) audio.currentTime = at;
    audio.play().catch((e) => {
      // Pausing before play() settles is not a failure.
      if (e instanceof DOMException && e.name === "AbortError") return;
      set({ error: String(e), playing: false });
    });
  },
  toggle() {
    if (!state.track) return;
    if (audio.paused) player.play(state.track);
    else audio.pause();
  },
  pause() {
    audio.pause();
  },
  seek(seconds: number) {
    const end = state.duration ?? Number.POSITIVE_INFINITY;
    audio.currentTime = Math.min(Math.max(0, seconds), end);
    notifyPosition();
  },
  close() {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    set({ track: null, playing: false, duration: null, error: null });
    if ("mediaSession" in navigator) navigator.mediaSession.metadata = null;
  },
  /** Keep the bar's title in step with a rename. */
  rename(songId: number, title: string) {
    if (state.track?.songId !== songId || state.track.title === title) return;
    const track = { ...state.track, title };
    set({ track });
    updateMediaSession(track);
  },
  /** A deleted song can't play on. */
  forget(songId: number) {
    if (state.track?.songId === songId) player.close();
  },
};

export function usePlayer(): State {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
  );
}

/** The playhead in seconds; re-renders a few times a second while playing, so keep it local. */
export function usePosition(): number {
  return useSyncExternalStore(
    (listener) => {
      positionListeners.add(listener);
      return () => positionListeners.delete(listener);
    },
    () => audio.currentTime,
  );
}

// Peaks are cached by the server too; this saves the request when a view is opened again.
const peaksCache = new Map<string, Promise<Peaks>>();

export function loadPeaks(songId: number, buckets: number): Promise<Peaks> {
  const key = `${songId}/${buckets}`;
  let peaks = peaksCache.get(key);
  if (!peaks) {
    peaks = api.peaks(songId, buckets);
    peaks.catch(() => peaksCache.delete(key));
    peaksCache.set(key, peaks);
  }
  return peaks;
}
