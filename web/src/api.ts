export type Mode = "full" | "melody" | "off";
export type Precision = "8bit" | "bf16";
export type Status = "queued" | "running" | "done" | "failed" | "cancelled";
export type Stage = "planning" | "semantic generation" | "synthesis" | "decoding";

export interface SongRequest {
  style: string;
  lyrics: string;
  mode: Mode;
  seed: number | null;
  precision: Precision;
  steps: 8 | 32;
}

export interface Live {
  stage: Stage | null;
  tokens?: number;
  completed?: number;
  total?: number;
}

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
}

export interface LibraryUsage {
  songs: number;
  bytes_used: number;
  bytes_free: number;
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
};

export interface Deleted {
  job_id: number;
  song_id: number;
}

/** Subscribes to job snapshots. EventSource reconnects by itself; `onConnect` runs on every
 * (re)connection so the caller can reload anything that changed while it was disconnected. */
export function watchJobs(
  onJob: (job: Job) => void,
  onDeleted: (deleted: Deleted) => void,
  onConnect: () => void,
): () => void {
  const source = new EventSource("/api/events");
  source.onopen = onConnect;
  source.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "job") onJob(message.job);
    if (message.type === "deleted") onDeleted(message);
  };
  return () => source.close();
}
