import { useCallback, useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { api, FINAL_STEPS, type Job, type Song } from "./api";
import { PauseIcon, PlayIcon } from "./icons";
import { claimAudio, onAudioClaimed } from "./player";
import { useResolvedTheme } from "./theme";
import { formatClock } from "./PlayerUI";
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
  // What the strip shows; updated a few times a second while a Take plays.
  const [clock, setClock] = useState(0);
  // The Take Space resumes after a pause.
  const last = useRef<number | null>(null);

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
  const byId = new Map((songs ?? []).map((song) => [song.id, song]));
  const moveTime = useCallback((seconds: number) => {
    time.current = seconds;
    setClock(seconds);
    setSharedTime({ seconds });
  }, []);
  const tick = useCallback((seconds: number) => {
    time.current = seconds;
    setClock(seconds);
  }, []);
  // Stable, so a card's play effect only runs when `playing` really changes.
  const stop = useCallback(() => setPlaying(null), []);
  const play = useCallback((songId: number) => {
    claimAudio("compare");
    last.current = songId;
    setPlaying(songId);
  }, []);
  // The player bar or the Score's preview starting stops the Takes.
  useEffect(() => onAudioClaimed("compare", stop), [stop]);

  // 1–9 play a Take, Space plays or pauses, S stars the Take playing (or last played).
  const ready = members.filter((job) => job.status === "done" && job.song_id !== null);
  const keys = useRef({ members, ready, playing, byId });
  keys.current = { members, ready, playing, byId };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]")) return;
      const { members, playing, byId } = keys.current;
      const digit = Number(event.key);
      if (Number.isInteger(digit) && digit >= 1 && digit <= members.length) {
        const songId = members[digit - 1].song_id;
        if (songId === null || members[digit - 1].status !== "done") return;
        event.preventDefault();
        if (playing === songId) stop();
        else play(songId);
      } else if (event.key === " " && !target.closest("a, [role=slider]") && (!target.closest("button") || target.closest("button.play"))) {
        // Ahead of the player bar's own Space handler, which listens on the bubbling side. A
        // focused play button (left focused by a click) means play/pause here, not "press me
        // again", or Space after switching Takes would restart the clicked one.
        event.preventDefault();
        event.stopPropagation();
        if (playing !== null) stop();
        else if (last.current !== null) play(last.current);
        else if (keys.current.ready[0]?.song_id != null) play(keys.current.ready[0].song_id);
      } else if (event.key === "s" || event.key === "S") {
        const songId = playing ?? last.current;
        const song = songId !== null ? byId.get(songId) : undefined;
        if (!song) return;
        event.preventDefault();
        api.star(song.id, !song.starred).then(onSong).catch(() => undefined);
      }
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [play, stop, onSong]);

  if (members.length === 0) {
    return (
      <section className="compare" aria-label="Compare">
        <a className="back" href="#/library">
          ← Library
        </a>
        <div className="card">
          {loadError ? <p className="error">Could not load this group: {loadError}</p> : <p className="muted">Loading…</p>}
        </div>
      </section>
    );
  }

  const request = members[0].request;
  const leadSong = members[0].song_id !== null ? byId.get(members[0].song_id) : undefined;
  const finals = jobs.filter((job) => job.source_song_id !== null);

  return (
    <section className="compare" aria-label="Compare">
      <a className="back" href="#/library">
        ← Library
      </a>
      <div className="compare-head">
        <div>
          <h1>{leadSong?.title ?? members[0].title}</h1>
          <p>
            {members.length} takes · {ready.length} ready ·{" "}
            {request.steps < FINAL_STEPS ? `quick drafts (${request.steps} steps)` : `${request.steps} steps`} ·{" "}
            {request.style}
          </p>
        </div>
        <div className="keys" aria-label="Keyboard shortcuts">
          <span>
            <kbd>1</kbd>–<kbd>{members.length}</kbd> switch take
          </span>
          <span>
            <kbd>Space</kbd> play / pause
          </span>
          <span>
            <kbd>S</kbd> star
          </span>
        </div>
      </div>

      <div className="card playhead-strip">
        <strong>Shared playhead</strong>
        <span className="muted">Switching takes keeps your place, so you hear the same moment in each.</span>
        <span className="time" aria-live="off">
          {formatClock(clock)}
        </span>
      </div>

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
            onPlay={play}
            onStop={stop}
            onMoveTime={moveTime}
            onTick={tick}
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
  onTick: (seconds: number) => void;
  onJob: (job: Job) => void;
  onSong: (song: Song) => void;
}

function TakeCard(props: CardProps) {
  const { job, index, song, final, playing, onPlay, onStop, onJob, onSong } = props;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const starred = song?.starred ?? job.starred ?? false;
  const finalActive = final && ["queued", "running", "done"].includes(final.status);
  const ready = job.status === "done" && job.song_id !== null;
  const n = index + 1;

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
    <li className={`card take${starred ? " starred" : ""}${playing ? " playing" : ""}`}>
      <div className="take-head">
        {ready && (
          <button
            type="button"
            className="play"
            aria-label={`${playing ? "Pause" : "Play"} take ${n}`}
            aria-pressed={playing}
            onClick={() => (playing ? onStop() : onPlay(job.song_id as number))}
          >
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
        )}
        <div className="row-text">
          <strong>
            Take {n} {ready && <kbd>{n}</kbd>}
          </strong>
          <div className="muted">
            seed {job.request.seed}
            {job.audio_seconds !== null && ` · ${formatClock(job.audio_seconds)}`}
          </div>
        </div>
        {ready ? (
          <button
            type="button"
            className={`star${starred ? " on" : ""}`}
            aria-pressed={starred}
            aria-label={`${starred ? "Unstar" : "Star"} take ${n}`}
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

      {ready && <Player {...props} songId={job.song_id as number} onError={setPlayError} />}
      {playError && <p className="error small">{playError}</p>}

      {ready && (
        <div className="actions">
          {job.request.steps < FINAL_STEPS && !finalActive && (
            <>
              <button
                type="button"
                className={starred ? "primary" : undefined}
                disabled={busy}
                onClick={() => act(() => api.finalize(job.song_id as number), onJob)}
              >
                {starred ? "Finalize this take" : "Finalize"}
              </button>
              {starred && <span className="muted small">Full quality, {FINAL_STEPS} steps</span>}
            </>
          )}
          {final && finalActive && (
            <span className="small">
              {final.status === "done" ? "✓ Finalized" : `Final ${final.status}…`} <a href="#/library">Library</a>
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
  onStop,
  onMoveTime,
  onTick,
  onError,
}: CardProps & { songId: number; onError: (error: string | null) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const surfer = useRef<WaveSurfer | null>(null);
  // WaveSurfer reads its colours once, so a theme change draws it again.
  const theme = useResolvedTheme();

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
          height: 72,
          barWidth: 2,
          barGap: 2,
          barRadius: 2,
          normalize: true,
          waveColor: color("--wave"),
          progressColor: color("--accent"),
          cursorColor: color("--text"),
          cursorWidth: 2,
        });
        ws.on("interaction", (seconds) => onMoveTime(seconds));
        surfer.current = ws;
      })
      .catch((e) => onError(String(e)));
    return () => {
      cancelled = true;
      surfer.current?.destroy();
      surfer.current = null;
    };
  }, [songId, onMoveTime, onError, theme]);

  // Start or stop this Take when the shared playhead moves to or away from it.
  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    if (playing) {
      element.currentTime = time.current;
      element.play().catch((e) => {
        // Switching Takes pauses this one before its play() settles; that is not a failure.
        if (e instanceof DOMException && e.name === "AbortError") return;
        onError(String(e));
        onStop();
      });
    } else if (!element.paused) {
      element.pause();
    }
  }, [playing, time, onStop, onError]);

  // A click on any waveform moves every Take there, the playing one included.
  useEffect(() => {
    const element = audio.current;
    if (element && Math.abs(element.currentTime - sharedTime.seconds) > 0.05) {
      element.currentTime = sharedTime.seconds;
    }
  }, [sharedTime]);

  return (
    <>
      <div ref={container} className="waveform" aria-label="Waveform" />
      <audio
        ref={audio}
        preload="metadata"
        src={api.audioUrl(songId)}
        onTimeUpdate={(e) => {
          if (playing) onTick(e.currentTarget.currentTime);
        }}
        onEnded={() => {
          onTick(0);
          onStop();
        }}
      />
    </>
  );
}

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}
