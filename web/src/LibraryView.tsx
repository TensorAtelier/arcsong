import { useEffect, useMemo, useState } from "react";
import { api, type Deleted, type Job, type LibraryUsage, type Song, type SongRequest } from "./api";
import { formatBytes, formatDate, formatSeconds } from "./format";

interface Props {
  songs: Song[] | null;
  error: string | null;
  onDeleted: (deleted: Deleted) => void;
  onRerun: (job: Job) => void;
  onEdit: (request: SongRequest) => void;
}

const MODES: Record<SongRequest["mode"], string> = {
  full: "Melody + chords",
  melody: "Melody only",
  off: "Off (no Score)",
};

export default function LibraryView({ songs, error, onDeleted, onRerun, onEdit }: Props) {
  const [filter, setFilter] = useState("");
  const [usage, setUsage] = useState<LibraryUsage | null>(null);

  useEffect(() => {
    api.library().then(setUsage).catch(() => setUsage(null));
  }, [songs]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!songs || !needle) return songs ?? [];
    return songs.filter((song) =>
      `${song.request.style}\n${song.request.lyrics}`.toLowerCase().includes(needle),
    );
  }, [songs, filter]);

  return (
    <section className="panel library" aria-label="Library">
      <div className="library-head">
        <h2>Library</h2>
        {usage && (
          <p className="muted small" data-testid="usage">
            {usage.songs} {usage.songs === 1 ? "song" : "songs"} · {formatBytes(usage.bytes_used)} used ·{" "}
            {formatBytes(usage.bytes_free)} free
          </p>
        )}
      </div>
      <input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter by style or lyrics"
        aria-label="Filter songs"
      />
      {error && <p className="error">Could not load songs: {error}</p>}
      {songs === null && !error && <p className="muted">Loading…</p>}
      {songs?.length === 0 && <p className="muted">No songs yet. Make one in Create.</p>}
      {songs && songs.length > 0 && shown.length === 0 && (
        <p className="muted">No songs match “{filter}”.</p>
      )}
      <ol className="jobs">
        {shown.map((song) => (
          <SongCard key={song.id} song={song} onDeleted={onDeleted} onRerun={onRerun} onEdit={onEdit} />
        ))}
      </ol>
    </section>
  );
}

interface CardProps {
  song: Song;
  onDeleted: (deleted: Deleted) => void;
  onRerun: (job: Job) => void;
  onEdit: (request: SongRequest) => void;
}

function SongCard({ song, onDeleted, onRerun, onEdit }: CardProps) {
  const { request } = song;
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run<T>(action: () => Promise<T>, then: (value: T) => void) {
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
    <li className="job song">
      <div className="job-head">
        <span className="job-title" title={request.style}>
          {request.style}
        </span>
        <span className="muted small">#{song.id}</span>
      </div>
      <div className="muted small">
        {formatDate(song.created_at)}
        {song.audio_seconds !== null && <> · {formatSeconds(song.audio_seconds)}</>} ·{" "}
        {formatBytes(song.bytes)}
      </div>
      <audio controls preload="none" src={api.audioUrl(song.id)} />

      <details>
        <summary className="small">Settings</summary>
        <dl className="settings">
          <dt>Planning</dt>
          <dd>{MODES[request.mode]}</dd>
          <dt>Quality</dt>
          <dd>{request.steps} steps</dd>
          <dt>Precision</dt>
          <dd>{request.precision}</dd>
          <dt>Seed</dt>
          <dd>{request.seed}</dd>
        </dl>
        {request.lyrics.trim() ? (
          <pre className="lyrics">{request.lyrics}</pre>
        ) : (
          <p className="muted small">No lyrics (instrumental).</p>
        )}
      </details>

      <div className="actions">
        <a className="button" href={api.downloadUrl(song.id, "flac")} download>
          FLAC
        </a>
        <a className="button" href={api.downloadUrl(song.id, "wav")} download>
          WAV
        </a>
        <button type="button" disabled={busy} onClick={() => run(() => api.create(request), onRerun)}>
          Re-run
        </button>
        <button type="button" disabled={busy} onClick={() => onEdit(request)}>
          Edit in Create
        </button>
        {!confirming && (
          <button type="button" className="danger" disabled={busy} onClick={() => setConfirming(true)}>
            Delete
          </button>
        )}
      </div>
      {confirming && (
        <div className="confirm" role="alertdialog" aria-label="Confirm delete">
          <span>Delete this song and its files permanently?</span>
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={() =>
              run(
                () => api.deleteSong(song.id),
                () => onDeleted({ song_id: song.id, job_id: song.job_id }),
              )
            }
          >
            Delete permanently
          </button>
          <button type="button" disabled={busy} onClick={() => setConfirming(false)}>
            Keep
          </button>
        </div>
      )}
      {actionError && <p className="error small">{actionError}</p>}
    </li>
  );
}
