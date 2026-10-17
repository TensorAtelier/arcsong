import { useEffect, useState } from "react";
import { api, FINAL_STEPS, type Job, type Live, type Song, type Stage } from "./api";
import { formatSeconds } from "./format";
import { formatClock, PlayButton, songTrack } from "./PlayerUI";

const TRANSCRIBING: { key: Stage; label: string }[] = [{ key: "transcribing", label: "Transcribing the recording" }];

const STAGES: { key: Stage; label: string }[] = [
  { key: "planning", label: "Writing the Score" },
  { key: "semantic generation", label: "Generating the song" },
  { key: "synthesis", label: "Synthesizing audio" },
  { key: "decoding", label: "Decoding audio" },
];

const FINISHED_SHOWN = 5;
const FAILURES_SHOWN = 3;

interface Props {
  jobs: Job[];
  songs: Song[] | null;
  onChanged: (job: Job) => void;
  error: string | null;
}

/** Create's right-hand column: what is rendering, what went wrong, and what just finished. */
export default function QueuePanel({ jobs, songs, onChanged, error }: Props) {
  // Failures the user has dismissed this session.
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  // Group id -> member ids, oldest first, to label "Take 2 of 4".
  const groups = new Map<number, number[]>();
  for (const job of [...jobs].sort((a, b) => a.id - b.id)) {
    if (job.group_id !== null) groups.set(job.group_id, [...(groups.get(job.group_id) ?? []), job.id]);
  }
  const label = (job: Job) => describeJob(job, groups);

  const running = jobs.filter((job) => job.status === "running").sort((a, b) => a.id - b.id);
  const queued = jobs.filter((job) => job.status === "queued").sort((a, b) => a.id - b.id);
  const failed = jobs.filter((job) => job.status === "failed" && !dismissed.has(job.id)).slice(0, FAILURES_SHOWN);
  const finished = jobs.filter((job) => job.status === "done").slice(0, FINISHED_SHOWN);
  const byId = new Map((songs ?? []).map((song) => [song.id, song]));

  // The group of the Take rendering now, for "2 of 4 done" and the Compare link.
  const groupId = running[0]?.group_id ?? queued[0]?.group_id ?? null;
  const members = groupId !== null ? jobs.filter((job) => job.group_id === groupId) : [];
  const ready = members.filter((job) => job.status === "done").length;

  return (
    <aside className="queue" aria-label="Queue">
      <section className="card" aria-label="Rendering">
        <div className="queue-head">
          <h2>Rendering</h2>
          {groupId !== null ? (
            <span className="muted">
              {ready} of {members.length} done
            </span>
          ) : (
            queued.length > 0 && <span className="muted">{queued.length} waiting</span>
          )}
        </div>
        {error && <p className="error small">Could not load jobs: {error}</p>}
        {running.length === 0 && queued.length === 0 && (
          <p className="muted small">Nothing is rendering. What you make shows up here while it renders.</p>
        )}
        {running.map((job) => (
          <Running key={job.id} job={job} label={label(job)} onChanged={onChanged} />
        ))}
        {queued.length > 0 && (
          <ol className="waiting" aria-label="Waiting">
            {queued.map((job, index) => (
              <Waiting key={job.id} job={job} label={label(job)} next={index === 0} onChanged={onChanged} />
            ))}
          </ol>
        )}
        {groupId !== null && ready > 0 && (
          <a className="compare-link" href={`#/compare/${groupId}`}>
            Compare the {ready === 1 ? "ready take" : `${ready} ready takes`} →
          </a>
        )}
      </section>

      {failed.map((job) => (
        <Failure
          key={job.id}
          job={job}
          onChanged={onChanged}
          onDismiss={() => setDismissed((current) => new Set(current).add(job.id))}
        />
      ))}

      {finished.length > 0 && (
        <section className="card" aria-label="Just finished">
          <div className="queue-head">
            <h2>Just finished</h2>
            <a href="#/library">Library →</a>
          </div>
          <ol className="finished">
            {finished.map((job) => {
              const song = job.song_id !== null ? byId.get(job.song_id) : undefined;
              return (
                <li key={job.id}>
                  {song ? (
                    <PlayButton track={songTrack(song)} />
                  ) : job.song_id !== null ? (
                    <PlayButton
                      track={{ songId: job.song_id, title: job.title, subtitle: job.request.style, seconds: job.audio_seconds }}
                    />
                  ) : (
                    <a className="button play small" href={`#/score/job/${job.id}`} aria-label={`Open the Score of ${job.title}`}>
                      ♪
                    </a>
                  )}
                  <div className="row-text">
                    <div className="row-title" title={song?.title ?? job.title}>
                      {song?.title ?? job.title}
                    </div>
                    <div className="row-meta">
                      {label(job)}
                      {job.kind !== "take" && (
                        <>
                          {" · "}
                          <a href={`#/score/job/${job.id}`}>Open the Score</a>
                        </>
                      )}
                    </div>
                  </div>
                  {job.audio_seconds !== null && <span className="clock">{formatClock(job.audio_seconds)}</span>}
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </aside>
  );
}

/** "Take 2 of 4 · seed 4243 · quick draft", "Final", "Score", … */
function describeJob(job: Job, groups: Map<number, number[]>): string {
  const parts: string[] = [];
  if (job.kind === "score") parts.push("Score only");
  else if (job.kind === "cover") parts.push("Cover");
  else if (job.source_song_id !== null) parts.push("Final");
  const group = job.group_id !== null ? groups.get(job.group_id) : undefined;
  if (group) parts.push(`Take ${group.indexOf(job.id) + 1} of ${group.length}`);
  parts.push(`seed ${job.request.seed}`);
  if (job.kind === "take" && job.source_song_id === null) {
    parts.push(job.request.steps < FINAL_STEPS ? "quick draft" : "full quality");
  }
  if (job.request.abc) parts.push("from an edited Score");
  return parts.join(" · ");
}

function useCancel(job: Job, onChanged: (job: Job) => void) {
  const [error, setError] = useState<string | null>(null);
  async function cancel() {
    setError(null);
    try {
      onChanged(await api.cancel(job.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return { cancel, error };
}

function Running({ job, label, onChanged }: { job: Job; label: string; onChanged: (job: Job) => void }) {
  const { cancel, error } = useCancel(job, onChanged);
  return (
    <div className="running">
      <div className="running-head">
        <strong title={job.title}>{job.title}</strong>
        {job.started_at && (
          <span className="left">
            <Elapsed since={job.started_at} />
          </span>
        )}
      </div>
      <span className="muted small">{label}</span>
      <Progress live={job.live} stages={stagesFor(job)} onCancel={cancel} />
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

function Waiting({ job, label, next, onChanged }: { job: Job; label: string; next: boolean; onChanged: (job: Job) => void }) {
  const { cancel, error } = useCancel(job, onChanged);
  return (
    <li>
      <span title={job.title}>
        {job.group_id !== null ? label.split(" · ")[0] : job.title} · waiting
      </span>
      <span>
        {next && "next "}
        <button type="button" className="link" aria-label={`Cancel ${job.title}`} onClick={() => void cancel()}>
          Cancel
        </button>
      </span>
      {error && <span className="error">{error}</span>}
    </li>
  );
}

function Failure({ job, onChanged, onDismiss }: { job: Job; onChanged: (job: Job) => void; onDismiss: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reason = lastLine(job.error ?? "It stopped without a reason.");

  async function retry() {
    setBusy(true);
    setError(null);
    try {
      onChanged(
        job.kind === "score"
          ? await api.createScore(job.request)
          : job.source_song_id !== null
            ? await api.finalize(job.source_song_id)
            : await api.create(job.request),
      );
      onDismiss();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card alert" role="alert">
      <strong>Stopped: {job.title}</strong>
      <span className="muted">{reason}</span>
      <div className="actions">
        {job.kind !== "cover" && (
          <button type="button" className="primary" disabled={busy} onClick={() => void retry()}>
            Retry
          </button>
        )}
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
      {job.error && job.error.trim() !== reason && (
        <details className="error-details">
          <summary className="small">Details</summary>
          <pre>{job.error}</pre>
        </details>
      )}
      {error && <p className="error small">{error}</p>}
    </section>
  );
}

function stagesFor(job: Job) {
  if (job.kind === "cover") return TRANSCRIBING;
  return job.kind === "score" ? STAGES.slice(0, 1) : STAGES;
}

interface ProgressProps {
  live: Live | null;
  stages?: typeof STAGES;
  onCancel?: () => void;
}

/** Stages as segments, the current one filling up, and a line saying where it is. */
export function Progress({ live, stages = STAGES, onCancel }: ProgressProps) {
  const current = stages.findIndex((s) => s.key === live?.stage);
  const done = live?.total ? Math.round(((live.completed ?? 0) / live.total) * 100) : 0;
  return (
    <div className="progress">
      <ol
        className="stagebar"
        aria-label={current >= 0 ? `Stage ${current + 1} of ${stages.length}` : "Starting"}
        style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}
      >
        {stages.map((stage, index) => (
          <li
            key={stage.key}
            title={stage.label}
            className={index < current ? "past" : index === current ? "current" : "future"}
            aria-current={index === current ? "step" : undefined}
            style={index === current ? ({ "--done": `${done}%` } as React.CSSProperties) : undefined}
          />
        ))}
      </ol>
      <div className="running-foot">
        <span>{describe(live)}</span>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function describe(live: Live | null): string {
  if (!live?.stage) return "Loading the model…";
  const label = [...STAGES, ...TRANSCRIBING].find((s) => s.key === live.stage)?.label ?? live.stage;
  if (live.total) return `${label} · step ${(live.completed ?? 0).toLocaleString()} of ${live.total.toLocaleString()}`;
  if (live.tokens) return `${label} · ${live.tokens.toLocaleString()} tokens`;
  return `${label}…`;
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);
  return <>{formatSeconds(Math.max(0, now - since))} in</>;
}

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}
