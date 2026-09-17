import { useEffect, useState } from "react";
import { api, type Job, type Live, type Stage } from "./api";
import { formatSeconds } from "./format";

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
  // Group id -> member ids, oldest first, to label "Take 2 of 4".
  const groups = new Map<number, number[]>();
  for (const job of [...jobs].sort((a, b) => a.id - b.id)) {
    if (job.group_id !== null) groups.set(job.group_id, [...(groups.get(job.group_id) ?? []), job.id]);
  }
  return (
    <section className="panel" aria-label="Queue">
      <h2>Queue</h2>
      {error && <p className="error">Could not load jobs: {error}</p>}
      {jobs.length === 0 && !error && <p className="muted">No songs yet.</p>}
      <ol className="jobs">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} group={job.group_id !== null ? groups.get(job.group_id) : undefined} onChanged={onChanged} />
        ))}
      </ol>
    </section>
  );
}

interface CardProps {
  job: Job;
  /** The ids of this job's Variations group, oldest first. */
  group: number[] | undefined;
  onChanged: (job: Job) => void;
}

function JobCard({ job, group, onChanged }: CardProps) {
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
      {group && job.group_id !== null && (
        <div className="small">
          Take {group.indexOf(job.id) + 1} of {group.length} ·{" "}
          <a href={`#/compare/${job.group_id}`}>Compare</a>
        </div>
      )}
      {job.source_song_id !== null && <div className="small">Final of song #{job.source_song_id}</div>}

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

export function Progress({ live }: { live: Live | null }) {
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

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}
