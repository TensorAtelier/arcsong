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
};

/** Subscribes to job snapshots; reconnects automatically (EventSource does). */
export function watchJobs(onJob: (job: Job) => void): () => void {
  const source = new EventSource("/api/events");
  source.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "job") onJob(message.job);
  };
  return () => source.close();
}
