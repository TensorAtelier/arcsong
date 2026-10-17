import { type KeyboardEvent, type PointerEvent, useEffect, useId, useMemo, useState } from "react";
import { api, type Song } from "./api";
import { PauseIcon, PlayIcon } from "./icons";
import { loadPeaks, player, type Track, usePlayer, usePosition } from "./player";

/** A Track for the player bar from a Library song. */
export function songTrack(song: Pick<Song, "id" | "title" | "request" | "audio_seconds">): Track {
  return { songId: song.id, title: song.title, subtitle: song.request.style, seconds: song.audio_seconds };
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Play or pause `track`: pausing only when it is the one playing. */
export function PlayButton({ track, size = "small" }: { track: Track; size?: "small" | "large" }) {
  const { track: current, playing } = usePlayer();
  const active = current?.songId === track.songId && playing;
  return (
    <button
      type="button"
      className={`play ${size}`}
      aria-label={active ? `Pause ${track.title}` : `Play ${track.title}`}
      aria-pressed={active}
      onClick={() => (current?.songId === track.songId ? player.toggle() : player.play(track))}
    >
      {active ? <PauseIcon /> : <PlayIcon />}
    </button>
  );
}

interface WaveProps {
  songId: number;
  buckets: number;
  /** 0–1 of the song played, or null when this song isn't the one in the player. */
  progress: number | null;
  onSeek: (fraction: number) => void;
  label: string;
}

/** Min/max peaks as one path; the played part is the same path in the accent colour. */
export function Waveform({ songId, buckets, progress, onSeek, label }: WaveProps) {
  const clip = useId();
  const [amplitude, setAmplitude] = useState<number[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadPeaks(songId, buckets)
      .then((peaks) => {
        if (cancelled) return;
        const raw = peaks.max.map((high, i) => Math.max(Math.abs(high), Math.abs(peaks.min[i])));
        const top = Math.max(...raw, 1e-6);
        setAmplitude(raw.map((a) => a / top));
      })
      .catch(() => !cancelled && setAmplitude([]));
    return () => {
      cancelled = true;
    };
  }, [songId, buckets]);

  const path = useMemo(
    () =>
      (amplitude ?? [])
        .map((a, i) => {
          const h = Math.max(3, a * 88);
          return `M${i + 0.25} ${50 - h / 2}h0.5v${h}h-0.5z`;
        })
        .join(""),
    [amplitude],
  );
  const width = amplitude?.length || buckets;

  function seekFrom(event: PointerEvent<SVGSVGElement>) {
    // A click seeks without taking focus, so the keyboard focus ring stays for keyboards.
    event.preventDefault();
    const box = event.currentTarget.getBoundingClientRect();
    onSeek(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)));
  }

  function seekByKey(event: KeyboardEvent<SVGSVGElement>) {
    const step = event.key === "ArrowRight" ? 0.05 : event.key === "ArrowLeft" ? -0.05 : 0;
    if (!step) return;
    event.preventDefault();
    onSeek(Math.min(1, Math.max(0, (progress ?? 0) + step)));
  }

  return (
    <svg
      className={`wave${amplitude === null ? " loading" : ""}`}
      viewBox={`0 0 ${width} 100`}
      preserveAspectRatio="none"
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round((progress ?? 0) * 100)}
      onPointerDown={seekFrom}
      onKeyDown={seekByKey}
    >
      <clipPath id={clip}>
        <rect width={(progress ?? 0) * width} height="100" />
      </clipPath>
      <path className="wave-base" d={path} />
      {progress !== null && <path className="wave-played" d={path} clipPath={`url(#${clip})`} />}
    </svg>
  );
}

/** Play button, waveform and time for one song: the player in a Library or Queue row. */
export function SongPlayer({ track, buckets = 160 }: { track: Track; buckets?: number }) {
  const { track: current, duration } = usePlayer();
  const isCurrent = current?.songId === track.songId;
  const length = (isCurrent ? duration : null) ?? track.seconds;
  return (
    <div className={`song-player${isCurrent ? " current" : ""}`}>
      <PlayButton track={track} />
      {isCurrent ? (
        <CurrentWave track={track} buckets={buckets} length={length} />
      ) : (
        <>
          <Waveform
            songId={track.songId}
            buckets={buckets}
            progress={null}
            label={`Seek in ${track.title}`}
            onSeek={(fraction) => player.play(track, length ? fraction * length : 0)}
          />
          <span className="clock">{length !== null ? formatClock(length) : ""}</span>
        </>
      )}
    </div>
  );
}

/** The waveform of the song that is playing; split out so only it follows the playhead. */
function CurrentWave({ track, buckets, length }: { track: Track; buckets: number; length: number | null }) {
  const position = usePosition();
  return (
    <>
      <Waveform
        songId={track.songId}
        buckets={buckets}
        progress={length ? position / length : 0}
        label={`Seek in ${track.title}`}
        onSeek={(fraction) => (length ? player.seek(fraction * length) : undefined)}
      />
      <span className="clock">
        {formatClock(position)}
        {length !== null && ` / ${formatClock(length)}`}
      </span>
    </>
  );
}

/** The bar along the bottom of every view while a song is loaded. */
export function NowPlaying({ songs }: { songs: Song[] | null }) {
  const { track, error, duration } = usePlayer();

  // Space plays and pauses, unless something that takes typing or clicks has focus.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== " " || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, button, a, [contenteditable], [role=slider]")) return;
      event.preventDefault();
      player.toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!track) return null;
  // The Library's copy is fresher: it follows renames from any tab.
  const song = songs?.find((s) => s.id === track.songId);
  const live = song ? songTrack(song) : track;
  return (
    <section className="now-playing" aria-label="Now playing">
      <div className="now-playing-inner">
        <PlayButton track={live} size="large" />
        <div className="now-playing-text">
          <div className="now-playing-title" title={live.title}>
            {live.title}
          </div>
          <div className="now-playing-subtitle" title={live.subtitle}>
            {error ? <span className="error">{error}</span> : live.subtitle}
          </div>
        </div>
        <div className="now-playing-wave">
          <CurrentWave track={live} buckets={400} length={duration ?? live.seconds} />
        </div>
        <div className="bar-actions">
          <a className="button download" href={api.downloadUrl(live.songId, "flac")} download aria-label="Download FLAC" title="Download FLAC">
            ↓
          </a>
          <button type="button" className="icon-button" aria-label="Close the player" title="Close the player" onClick={() => player.close()}>
            ×
          </button>
        </div>
      </div>
    </section>
  );
}

interface TitleProps {
  song: Pick<Song, "id" | "title" | "title_set">;
  onSong: (song: Song) => void;
  /** Set to rename from elsewhere, e.g. a menu; the title then has no Rename button of its own. */
  editing?: boolean;
  onEditingChange?: (editing: boolean) => void;
}

/** A song's title; Rename (or a double click) edits it in place. Empty goes back to the default. */
export function SongTitle({ song, onSong, editing: controlled, onEditingChange }: TitleProps) {
  const [own, setOwn] = useState(false);
  const editing = controlled ?? own;
  const setEditing = (next: boolean) => (onEditingChange ? onEditingChange(next) : setOwn(next));
  const [text, setText] = useState(song.title);
  useEffect(() => {
    if (editing) setText(song.title);
    // Only when editing starts; typing must not be overwritten by a re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const next = text.trim();
    if (next === song.title || (!next && !song.title_set)) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.rename(song.id, next || null);
      onSong(updated);
      player.rename(updated.id, updated.title);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <span className="title-edit">
        <input
          autoFocus
          aria-label="Song title"
          value={text}
          maxLength={120}
          disabled={saving}
          placeholder="Leave empty for the default title"
          onChange={(e) => setText(e.target.value)}
          onBlur={() => void save()}
          onKeyDown={(e) => {
            if (e.key === "Enter") void save();
            if (e.key === "Escape") {
              setText(song.title);
              setEditing(false);
            }
          }}
        />
        {error && <span className="error small">{error}</span>}
      </span>
    );
  }
  return (
    <span className="title-view">
      <span
        className="song-title"
        title={song.title}
        onDoubleClick={() => {
          setText(song.title);
          setEditing(true);
        }}
      >
        {song.title}
      </span>
      {controlled === undefined && (
      <button
        type="button"
        className="link rename"
        aria-label={`Rename ${song.title}`}
        onClick={() => {
          setText(song.title);
          setEditing(true);
        }}
      >
        Rename
      </button>
      )}
    </span>
  );
}
