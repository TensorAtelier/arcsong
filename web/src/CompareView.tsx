import { useCallback, useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { api, FINAL_STEPS, type Job, type Song } from "./api";
import { Progress } from "./QueuePanel";

const BUCKETS = 600;

/** A move of the shared playhead, e.g. from a waveform click. */
interface Seek {
  seconds: number;
}

interface Props {
  groupId: number;
  jobs: Job[];
  songs: Song[] | null;
  onJob: (job: Job) => void;
  onSong: (song: Song) => void;
}

/** Variations side by side. One shared playhead: only one Take plays at a time, and starting
 * another continues from the same moment, so the same passage can be heard across Takes. */
export default function CompareView({ groupId, jobs, songs, onJob, onSong }: Props) {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  // A new object on every click, so clicking the same spot twice still moves every Take.
  const [sharedTime, setSharedTime] = useState<Seek>({ seconds: 0 });
  // The latest shared time without re-rendering every card on every audio tick.
  const time = useRef(0);

  useEffect(() => {
    api
      .group(groupId)
      .then((list) => {
        setLoadError(null);
        list.forEach(onJob);
      })
      .catch((error) => setLoadError(String(error)));
  }, [groupId, onJob]);

  const members = jobs.filter((job) => job.group_id === groupId).sort((a, b) => a.id - b.id);
  const moveTime = useCallback((seconds: number) => {
    time.current = seconds;
    setSharedTime({ seconds });
  }, []);
  // Stable, so a card's play effect only runs when `playing` really changes.
  const stop = useCallback(() => setPlaying(null), []);

  if (members.length === 0) {
    return (
      <section className="panel compare" aria-label="Compare">
        <h2>Compare</h2>
        {loadError ? <p className="error">Could not load this group: {loadError}</p> : <p className="muted">Loading…</p>}
        <p>
          <a href="#/library">Back to the Library</a>
        </p>
      </section>
    );
  }

  const request = members[0].request;
  const done = members.filter((job) => job.status === "done").length;
  const byId = new Map((songs ?? []).map((song) => [song.id, song]));
  const finals = jobs.filter((job) => job.source_song_id !== null);

  return (
    <section className="panel compare" aria-label="Compare">
      <div className="library-head">
        <h2>Compare</h2>
        <p className="muted small">
          {members.length} Takes · {done} ready · {request.steps} steps · {request.precision}
        </p>
      </div>
      <p className="compare-style" title={request.style}>
        {request.style}
      </p>
      <p className="hint">
        Play a Take, then press Play on another to hear the same moment. Click a waveform to move every
        Take there. Star your pick and Finalize it.
      </p>
      <ol className="takes">
        {members.map((job, index) => (
          <TakeCard
            key={job.id}
            job={job}
            index={index}
            song={job.song_id !== null ? byId.get(job.song_id) : undefined}
            final={job.song_id !== null ? latestFinal(finals, job.song_id) : undefined}
            playing={playing === job.song_id && job.song_id !== null}
            sharedTime={sharedTime}
            time={time}
            onPlay={setPlaying}
            onStop={stop}
            onMoveTime={moveTime}
            onJob={onJob}
            onSong={onSong}
          />
        ))}
      </ol>
    </section>
  );
}

function latestFinal(finals: Job[], songId: number): Job | undefined {
  return finals.filter((job) => job.source_song_id === songId).sort((a, b) => b.id - a.id)[0];
}

interface CardProps {
  job: Job;
  index: number;
  song: Song | undefined;
  final: Job | undefined;
  playing: boolean;
  sharedTime: Seek;
  time: React.MutableRefObject<number>;
  onPlay: (songId: number) => void;
  onStop: () => void;
  onMoveTime: (seconds: number) => void;
  onJob: (job: Job) => void;
  onSong: (song: Song) => void;
}

function TakeCard(props: CardProps) {
  const { job, index, song, final, playing, onJob, onSong } = props;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const starred = song?.starred ?? job.starred ?? false;
  const finalActive = final && ["queued", "running", "done"].includes(final.status);

  async function act<T>(action: () => Promise<T>, then: (value: T) => void) {
    setBusy(true);
    setActionError(null);
    try {
      then(await action());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`job take${starred ? " starred" : ""}${playing ? " playing" : ""}`}>
      <div className="job-head">
        <span className="job-title">
          Take {index + 1} <span className="muted small">seed {job.request.seed}</span>
        </span>
        {job.status === "done" && job.song_id !== null ? (
          <button
            type="button"
            className={`star${starred ? " on" : ""}`}
            aria-pressed={starred}
            aria-label={starred ? "Unstar this Take" : "Star this Take"}
            disabled={busy}
            onClick={() => act(() => api.star(job.song_id as number, !starred), onSong)}
          >
            {starred ? "★" : "☆"}
          </button>
        ) : (
          <span className={`badge ${job.status}`}>{job.status}</span>
        )}
      </div>

      {job.status === "running" && <Progress live={job.live} />}
      {job.status === "queued" && <p className="muted small">Waiting in the queue…</p>}
      {job.status === "failed" && <p className="error small">{lastLine(job.error ?? "failed")}</p>}

      {job.status === "done" && job.song_id !== null && <Player {...props} songId={job.song_id} />}

      {job.status === "done" && job.song_id !== null && (
        <div className="actions">
          {job.request.steps < FINAL_STEPS && !finalActive && (
            <button type="button" disabled={busy} onClick={() => act(() => api.finalize(job.song_id as number), onJob)}>
              Finalize ({FINAL_STEPS} steps)
            </button>
          )}
          {final && finalActive && (
            <span className="small">
              {final.status === "done" ? "✓ Finalized" : `Final ${final.status}…`}{" "}
              <a href="#/library">Library</a>
            </span>
          )}
          {final && final.status === "failed" && <span className="error small">The Final failed; try again.</span>}
        </div>
      )}
      {actionError && <p className="error small">{actionError}</p>}
    </li>
  );
}

function Player({
  songId,
  playing,
  sharedTime,
  time,
  onPlay,
  onStop,
  onMoveTime,
}: CardProps & { songId: number }) {
  const container = useRef<HTMLDivElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const surfer = useRef<WaveSurfer | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .peaks(songId, BUCKETS)
      .then((peaks) => {
        if (cancelled || !container.current || !audio.current) return;
        const style = getComputedStyle(document.documentElement);
        const color = (name: string) => style.getPropertyValue(name).trim();
        const amplitude = peaks.max.map((high, i) => Math.max(Math.abs(high), Math.abs(peaks.min[i])));
        const ws = WaveSurfer.create({
          container: container.current,
          media: audio.current,
          peaks: [amplitude],
          duration: peaks.duration,
          height: 56,
          barWidth: 2,
          barGap: 1,
          barRadius: 1,
          normalize: true,
          waveColor: color("--muted"),
          progressColor: color("--accent"),
          cursorColor: color("--text"),
        });
        ws.on("interaction", (seconds) => onMoveTime(seconds));
        surfer.current = ws;
        setDuration(peaks.duration);
      })
      .catch((e) => setError(String(e)));
    return () => {
      cancelled = true;
      surfer.current?.destroy();
      surfer.current = null;
    };
  }, [songId, onMoveTime]);

  // Start or stop this Take when the shared playhead moves to or away from it.
  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    if (playing) {
      element.currentTime = time.current;
      element.play().catch((e) => {
        // Switching Takes pauses this one before its play() settles; that is not a failure.
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(String(e));
        onStop();
      });
    } else if (!element.paused) {
      element.pause();
    }
  }, [playing, time, onStop]);

  // A click on any waveform moves every Take there, the playing one included.
  useEffect(() => {
    const element = audio.current;
    if (element && Math.abs(element.currentTime - sharedTime.seconds) > 0.05) {
      element.currentTime = sharedTime.seconds;
      setPosition(sharedTime.seconds);
    }
  }, [sharedTime]);

  return (
    <div className="player">
      <div ref={container} className="waveform" aria-label="Waveform" />
      <audio
        ref={audio}
        preload="metadata"
        src={api.audioUrl(songId)}
        onTimeUpdate={(e) => {
          const seconds = e.currentTarget.currentTime;
          setPosition(seconds);
          if (playing) time.current = seconds;
        }}
        onEnded={() => {
          time.current = 0;
          onStop();
        }}
      />
      <div className="player-bar">
        <button type="button" onClick={() => (playing ? onStop() : onPlay(songId))} aria-pressed={playing}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <span className="muted small">
          {formatClock(position)} / {duration !== null ? formatClock(duration) : "…"}
        </span>
      </div>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}
