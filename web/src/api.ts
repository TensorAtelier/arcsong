export type Mode = "full" | "melody" | "off";
export type Precision = "8bit" | "bf16";
export type Status = "queued" | "running" | "done" | "failed" | "cancelled";
export type Stage =
  | "planning"
  | "semantic generation"
  | "synthesis"
  | "decoding"
  /** A cover's own Stage, before any of those. */
  | "transcribing";

export interface CoverRequest {
  audio: File;
  style: string;
  lyrics: string;
  mode: Mode;
  precision: Precision;
  steps: 8 | 32;
  rights_confirmed: boolean;
}

export interface SongRequest {
  style: string;
  lyrics: string;
  mode: Mode;
  seed: number | null;
  precision: Precision;
  steps: 8 | 32;
  /** An edited Score to render instead of writing one. */
  abc?: string | null;
  /** A cover: the name of the recording it was transcribed from. */
  source_name?: string | null;
}

export interface ScoreReport {
  bpm: number;
  duration_seconds: number;
  voices: Record<"Vocal" | "Ins", { sounding_notes: number; measures: number; chords: number }>;
}

export interface ScoreCheck {
  ok: boolean;
  error: string | null;
  report: ScoreReport | null;
  diff: { match: boolean; differences: string[] } | null;
}

export interface ScoreJob {
  job: Job;
  abc: string | null;
  report: ScoreReport | null;
}

export interface SongScore {
  song_id: number;
  abc: string;
  report: ScoreReport | null;
  request: SongRequest & { seed: number };
}

export interface Live {
  stage: Stage | null;
  tokens?: number;
  completed?: number;
  total?: number;
}

export type JobKind = "take" | "score" | "cover";

export interface Job {
  id: number;
  status: Status;
  request: SongRequest & { seed: number };
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
  song_id: number | null;
  audio_seconds: number | null;
  live: Live | null;
  /** Variations share the id of their group's first job; null for a single job. */
  kind: JobKind;
  /** A Score job's ABC, once planning has finished. */
  score: string | null;
  group_id: number | null;
  /** A Final: the Draft song it was made from. */
  source_song_id: number | null;
  starred: boolean | null;
  /** Grows with every snapshot the server takes; keep the job with the highest. */
  seq: number;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
      : body.detail;
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export interface Song {
  id: number;
  job_id: number;
  audio_seconds: number | null;
  created_at: number;
  bytes: number;
  request: SongRequest & { seed: number };
  group_id: number | null;
  source_song_id: number | null;
  starred: boolean;
}

export interface Peaks {
  duration: number;
  min: number[];
  max: number[];
}

/** Takes below this many Synthesis steps are Drafts and can be finalized. */
export const FINAL_STEPS = 32;

export interface LibraryUsage {
  songs: number;
  bytes_used: number;
  bytes_free: number;
}

export type CheckStatus = "ok" | "warn" | "fail";

export interface Check {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
}

export interface Download {
  state: "idle" | "running" | "done" | "failed" | "cancelled";
  phase?: "starting" | "downloading" | "verifying";
  bytes?: number;
  bytes_total?: number;
  reason?: string;
  error?: string;
}

export interface SetupPart {
  id: "engine" | "covers" | string;
  label: string;
  summary: string;
  weights: Weights;
  download: Download;
  checks: Check[];
}

export interface Weights {
  dir: string;
  installed: boolean;
  bytes_total: number;
  bytes_present: number;
  /** Including partly downloaded files. */
  bytes_on_disk: number;
  missing: string[];
  stray: string[];
}

export interface Setup {
  /** Grows with every snapshot the server takes; keep the one with the highest. */
  seq: number;
  checks: Check[];
  /** The Engine's own checks (platform, runtime) are still running. */
  checking: boolean;
  /** The Song model and the optional Covers extra. */
  parts: SetupPart[];
  /** The Song model part's weights, which most of the page cares about. */
  weights: Weights;
  licence: {
    id: string;
    name: string;
    url: string;
    models: string[];
    acknowledged_at: number | null;
  };
  download: Download;
  /** Songs can be made: weights installed, no download running or failed. */
  can_render: boolean;
  /** `can_render` and the licence acknowledged. */
  ready: boolean;
}

function post<T>(url: string): Promise<T> {
  return fetch(url, { method: "POST" }).then((r) => json<T>(r));
}

export const api = {
  jobs: () => fetch("/api/jobs").then((r) => json<Job[]>(r)),
  create: (request: SongRequest) =>
    fetch("/api/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }).then((r) => json<Job>(r)),
  cancel: (id: number) =>
    fetch(`/api/jobs/${id}/cancel`, { method: "POST" }).then((r) => json<Job>(r)),
  audioUrl: (songId: number) => `/api/songs/${songId}/audio`,
  songs: () => fetch("/api/songs").then((r) => json<Song[]>(r)),
  library: () => fetch("/api/library").then((r) => json<LibraryUsage>(r)),
  deleteSong: (id: number) =>
    fetch(`/api/songs/${id}`, { method: "DELETE" }).then((r) => json<{ deleted: number }>(r)),
  downloadUrl: (id: number, format: "flac" | "wav") => `/api/songs/${id}/download?format=${format}`,
  createGroup: (request: SongRequest, count: number) =>
    fetch("/api/groups", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...request, count }),
    }).then((r) => json<Job[]>(r)),
  group: (id: number) => fetch(`/api/groups/${id}`).then((r) => json<Job[]>(r)),
  star: (songId: number, starred: boolean) =>
    fetch(`/api/songs/${songId}/star`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ starred }),
    }).then((r) => json<Song>(r)),
  finalize: (songId: number) => post<Job>(`/api/songs/${songId}/finalize`),
  peaks: (songId: number, buckets: number) =>
    fetch(`/api/songs/${songId}/peaks?buckets=${buckets}`).then((r) => json<Peaks>(r)),
  createCover: (request: CoverRequest) => {
    const body = new FormData();
    body.append("audio", request.audio);
    body.append("style", request.style);
    body.append("lyrics", request.lyrics);
    body.append("mode", request.mode);
    body.append("precision", request.precision);
    body.append("steps", String(request.steps));
    body.append("rights_confirmed", String(request.rights_confirmed));
    return fetch("/api/covers", { method: "POST", body }).then((r) => json<Job>(r));
  },
  createScore: (request: Omit<SongRequest, "abc">) =>
    fetch("/api/scores", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }).then((r) => json<Job>(r)),
  score: (jobId: number) => fetch(`/api/scores/${jobId}`).then((r) => json<ScoreJob>(r)),
  songScore: (songId: number) =>
    fetch(`/api/songs/${songId}/score`).then((r) => json<SongScore>(r)),
  checkScore: (abc: string, original: string | null) =>
    fetch("/api/score/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ abc, original }),
    }).then((r) => json<ScoreCheck>(r)),
  stripChords: (abc: string) =>
    fetch("/api/score/strip-chords", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ abc }),
    }).then((r) => json<{ abc: string }>(r)),
  setup: () => fetch("/api/setup").then((r) => json<Setup>(r)),
  runChecks: () => post<Setup>("/api/setup/checks"),
  acknowledgeLicence: () => post<Setup>("/api/setup/licence"),
  startDownload: (part = "engine") => post<Setup>(`/api/setup/download/${part}`),
  cancelDownload: (part = "engine") => post<Setup>(`/api/setup/download/${part}/cancel`),
};

export interface Deleted {
  job_id: number;
  song_id: number;
}

export interface EventHandlers {
  onJob: (job: Job) => void;
  onDeleted: (deleted: Deleted) => void;
  onSetup: (setup: Setup) => void;
  onSong: (song: Song) => void;
  /** Runs on every (re)connection, so the caller can reload what changed while disconnected. */
  onConnect: () => void;
}

/** Subscribes to the server's events. EventSource reconnects by itself. */
export function watchEvents(handlers: EventHandlers): () => void {
  const source = new EventSource("/api/events");
  source.onopen = handlers.onConnect;
  source.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "job") handlers.onJob(message.job);
    if (message.type === "deleted") handlers.onDeleted(message);
    if (message.type === "setup") handlers.onSetup(message.setup);
    if (message.type === "song") handlers.onSong(message.song);
  };
  return () => source.close();
}
