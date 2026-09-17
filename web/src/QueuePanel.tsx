import { useEffect, useState } from "react";
import { api, type Job, type Live, type Stage } from "./api";

const STAGES: { key: Stage; label: string }[] = [
  { key: "planning", label: "Writing the Score" },
  { key: "semantic generation", label: "Generating the song" },
  { key: "synthesis", label: "Synthesizing audio" },
  { key: "decoding", label: "Decoding audio" },
];

interface Props {
  jobs: Job[];
  onChanged: (job: Job) => void;
  error: string | null;
}

export default function QueuePanel({ jobs, onChanged, error }: Props) {
  return (
    <section className="panel" aria-label="Queue">
      <h2>Queue</h2>
      {error && <p className="error">Could not load jobs: {error}</p>}
      {jobs.length === 0 && !error && <p className="muted">No songs yet.</p>}
      <ol className="jobs">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} onChanged={onChanged} />
        ))}
      </ol>
    </section>
  );
}

function JobCard({ job, onChanged }: { job: Job; onChanged: (job: Job) => void }) {
  const [cancelError, setCancelError] = useState<string | null>(null);
  const active = job.status === "queued" || job.status === "running";

  async function cancel() {
    setCancelError(null);
    try {
      onChanged(await api.cancel(job.id));
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <li className={`job ${job.status}`}>
      <div className="job-head">
        <span className="job-title" title={job.request.style}>
          #{job.id} · {job.request.style}
        </span>
        <span className={`badge ${job.status}`}>{job.status}</span>
      </div>
      <div className="muted small">
        seed {job.request.seed} · {job.request.precision} · {job.request.steps} steps
        {job.status === "running" && job.started_at && <Elapsed since={job.started_at} />}
      </div>

      {job.status === "running" && <Progress live={job.live} />}

      {job.status === "done" && job.song_id !== null && (
        <>
          <audio controls preload="none" src={api.audioUrl(job.song_id)} />
          {job.audio_seconds !== null && (
            <div className="muted small">{formatSeconds(job.audio_seconds)} of audio</div>
          )}
        </>
      )}

      {job.status === "failed" && job.error && (
        <details className="error-details">
          <summary>{lastLine(job.error)}</summary>
          <pre>{job.error}</pre>
        </details>
      )}

      {active && (
        <button type="button" onClick={cancel}>
          Cancel
        </button>
      )}
      {cancelError && <p className="error">{cancelError}</p>}
    </li>
  );
}

function Progress({ live }: { live: Live | null }) {
  const current = STAGES.findIndex((s) => s.key === live?.stage);
  return (
    <div className="progress">
      <ol className="stages" aria-label="Stages">
        {STAGES.map((stage, index) => (
          <li
            key={stage.key}
            className={index < current ? "past" : index === current ? "current" : "future"}
            aria-current={index === current ? "step" : undefined}
          >
            {stage.label}
          </li>
        ))}
      </ol>
      <div className="small">{describe(live)}</div>
      {live?.total ? <progress max={live.total} value={live.completed ?? 0} /> : null}
    </div>
  );
}

function describe(live: Live | null): string {
  if (!live?.stage) return "Loading the model…";
  const label = STAGES.find((s) => s.key === live.stage)?.label ?? live.stage;
  if (live.total) return `${label} · step ${live.completed ?? 0} of ${live.total}`;
  if (live.tokens) return `${label} · ${live.tokens.toLocaleString()} tokens`;
  return `${label}…`;
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);
  return <> · {formatSeconds(Math.max(0, now - since))} elapsed</>;
}

function formatSeconds(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}
