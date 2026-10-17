import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { api, type Deleted, FINAL_STEPS, type Job, type LibraryUsage, type Song, type SongRequest } from "./api";
import { formatBytes, formatDate } from "./format";
import { artStyle } from "./icons";
import { SongPlayer, SongTitle, songTrack } from "./PlayerUI";

interface Props {
  songs: Song[] | null;
  /** Every job, to find each Draft's Final. */
  jobs: Job[];
  onJob: (job: Job) => void;
  onSong: (song: Song) => void;
  error: string | null;
  onDeleted: (deleted: Deleted) => void;
  onRerun: (job: Job) => void;
  onEdit: (request: SongRequest) => void;
}

type Show = "all" | "starred" | "drafts" | "finals";

const SHOWS: { id: Show; label: string }[] = [
  { id: "all", label: "All" },
  { id: "starred", label: "★ Starred" },
  { id: "drafts", label: "Drafts" },
  { id: "finals", label: "Finals" },
];

const MODES: Record<SongRequest["mode"], string> = {
  full: "Melody + chords",
  melody: "Melody only",
  off: "Off (no Score)",
};

/** A sketch (a Variations group and its Finals), or a song made on its own. */
type Entry = { kind: "sketch"; groupId: number; songs: Song[] } | { kind: "song"; song: Song };

const isDraft = (song: Song) => song.request.steps < FINAL_STEPS;

export default function LibraryView({ songs, jobs, onJob, onSong, error, onDeleted, onRerun, onEdit }: Props) {
  const [filter, setFilter] = useState("");
  const [show, setShow] = useState<Show>("all");
  const [usage, setUsage] = useState<LibraryUsage | null>(null);

  useEffect(() => {
    api.library().then(setUsage).catch(() => setUsage(null));
  }, [songs]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (songs ?? []).filter(
      (song) =>
        (show !== "starred" || song.starred) &&
        (show !== "drafts" || isDraft(song)) &&
        (show !== "finals" || !isDraft(song)) &&
        (!needle || `${song.title}\n${song.request.style}\n${song.request.lyrics}`.toLowerCase().includes(needle)),
    );
  }, [songs, filter, show]);

  const entries = useMemo(() => group(shown, songs ?? []), [shown, songs]);
  // Each group's members in render order, to number its Takes even when a filter hides some.
  const takeNumber = useMemo(() => {
    const members = new Map<number, number[]>();
    for (const job of [...jobs].sort((a, b) => a.id - b.id)) {
      if (job.group_id !== null) members.set(job.group_id, [...(members.get(job.group_id) ?? []), job.id]);
    }
    return (song: Song) => (song.group_id !== null ? (members.get(song.group_id)?.indexOf(song.job_id) ?? -1) + 1 : 0);
  }, [jobs]);

  const rowProps = { jobs, library: songs ?? [], onJob, onSong, onDeleted, onRerun, onEdit };
  const projects = new Set((songs ?? []).map((song) => song.group_id ?? `song-${song.id}`)).size;

  return (
    <section className="library" aria-label="Library">
      <div className="page-head">
        <div className="title">
          <h1>Library</h1>
          {usage && songs && (
            <span className="muted small" data-testid="usage">
              {projects} {projects === 1 ? "song" : "songs"} · {usage.songs} {usage.songs === 1 ? "take" : "takes"} ·{" "}
              {formatBytes(usage.bytes_used)} · {formatBytes(usage.bytes_free)} free
            </span>
          )}
        </div>
        <div className="tools">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search titles, styles, lyrics"
            aria-label="Search songs"
          />
          <div className="segmented" role="group" aria-label="Show">
            {SHOWS.map((choice) => (
              <button key={choice.id} type="button" aria-pressed={show === choice.id} onClick={() => setShow(choice.id)}>
                {choice.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className="error">Could not load songs: {error}</p>}
      {songs === null && !error && <p className="muted">Loading…</p>}
      {songs?.length === 0 && (
        <div className="card empty">
          No songs yet. <a href="#/">Make one in Create</a>.
        </div>
      )}
      {songs && songs.length > 0 && entries.length === 0 && (
        <div className="card empty">
          {filter.trim() ? `No songs match “${filter}”.` : `No ${SHOWS.find((s) => s.id === show)?.label.replace("★ ", "").toLowerCase()} songs yet.`}
        </div>
      )}

      {entries.map((entry) =>
        entry.kind === "sketch" ? (
          <Sketch key={`g${entry.groupId}`} groupId={entry.groupId} songs={entry.songs} takeNumber={takeNumber} {...rowProps} />
        ) : (
          <section key={entry.song.id} className="card project" aria-label={entry.song.title}>
            <SongRow song={entry.song} variant="song" {...rowProps} />
          </section>
        ),
      )}
    </section>
  );
}

/** Sketch groups gather their Takes and the Finals made from them; the newest work comes first. */
function group(shown: Song[], all: Song[]): Entry[] {
  const groupOf = new Map(all.map((song) => [song.id, song.group_id]));
  const sketches = new Map<number, Song[]>();
  const entries: { newest: number; entry: Entry }[] = [];
  for (const song of shown) {
    const groupId = song.group_id ?? (song.source_song_id !== null ? (groupOf.get(song.source_song_id) ?? null) : null);
    if (groupId === null) {
      entries.push({ newest: song.id, entry: { kind: "song", song } });
      continue;
    }
    if (!sketches.has(groupId)) sketches.set(groupId, []);
    sketches.get(groupId)!.push(song);
  }
  for (const [groupId, members] of sketches) {
    members.sort((a, b) => Number(isDraft(b)) - Number(isDraft(a)) || a.id - b.id);
    entries.push({ newest: Math.max(...members.map((s) => s.id)), entry: { kind: "sketch", groupId, songs: members } });
  }
  return entries.sort((a, b) => b.newest - a.newest).map((e) => e.entry);
}

interface RowProps {
  jobs: Job[];
  /** Every song, to tell whether a Final's Draft still exists. */
  library: Song[];
  onJob: (job: Job) => void;
  onSong: (song: Song) => void;
  onDeleted: (deleted: Deleted) => void;
  onRerun: (job: Job) => void;
  onEdit: (request: SongRequest) => void;
}

function Sketch({ groupId, songs, takeNumber, ...rowProps }: RowProps & { groupId: number; songs: Song[]; takeNumber: (song: Song) => number }) {
  const drafts = songs.filter(isDraft);
  const lead = drafts[0] ?? songs[0];
  const starred = drafts.filter((song) => song.starred);
  const finals = songs.filter((song) => !isDraft(song));
  const status = finals.length
    ? `Finalized${starred.length ? ` · ★ take ${takeNumber(starred[0])}` : ""}`
    : starred.length
      ? `★ take ${starred.map(takeNumber).join(", ")}`
      : "no pick yet";
  return (
    <section className="card project" aria-label={lead.title}>
      <div className="project-head">
        <div className="art large" aria-hidden="true" style={artStyle(lead.request.seed)} />
        <div className="row-text">
          <div className="title-line">
            <span className="song-title" title={lead.title}>
              {lead.title}
            </span>
            <span className="badge draft">
              Sketch · {drafts.length} {drafts.length === 1 ? "take" : "takes"} · {status}
            </span>
          </div>
          <div className="subtitle" title={lead.request.style}>
            {lead.request.style} · {formatDate(lead.created_at)}
          </div>
        </div>
        <a className="button primary" href={`#/compare/${groupId}`}>
          Compare &amp; pick
        </a>
      </div>
      <ol className="takes-list">
        {songs.map((song) => (
          <li key={song.id} className="take-row">
            <SongRow
              song={song}
              variant="take"
              name={isDraft(song) ? `Take ${takeNumber(song) || "?"}` : "Final"}
              {...rowProps}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}

function latestFinal(jobs: Job[], songId: number): Job | undefined {
  return jobs.filter((job) => job.source_song_id === songId).sort((a, b) => b.id - a.id)[0];
}

function SongRow({
  song,
  variant,
  name,
  jobs,
  library,
  onJob,
  onSong,
  onDeleted,
  onRerun,
  onEdit,
}: RowProps & { song: Song; variant: "take" | "song"; name?: string }) {
  const { request } = song;
  const draft = isDraft(song);
  const final = latestFinal(jobs, song.id);
  const finalActive = final && ["queued", "running", "done"].includes(final.status);
  const draftDeleted = song.source_song_id !== null && !library.some((s) => s.id === song.source_song_id);
  const [renaming, setRenaming] = useState(false);
  const [details, setDetails] = useState(false);
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

  const finalize = () => run(() => api.finalize(song.id), onJob);
  const star = (
    <button
      type="button"
      className={`star${song.starred ? " on" : ""}`}
      aria-pressed={song.starred}
      aria-label={song.starred ? `Unstar ${song.title}` : `Star ${song.title}`}
      disabled={busy}
      onClick={() => run(() => api.star(song.id, !song.starred), onSong)}
    >
      {song.starred ? "★" : "☆"}
    </button>
  );
  const finalState =
    final && (final.status === "queued" || final.status === "running") ? (
      <span className="row-status">Final {final.status}…</span>
    ) : final?.status === "done" ? (
      <span className="row-status">✓ Finalized</span>
    ) : null;

  const menu = (
    <Menu label={`More for ${song.title}`}>
      <button type="button" role="menuitem" onClick={() => setRenaming(true)}>
        Rename
      </button>
      {request.mode !== "off" && (
        <a role="menuitem" href={`#/score/song/${song.id}`}>
          Open the Score
        </a>
      )}
      {variant === "song" && song.group_id !== null && (
        <a role="menuitem" href={`#/compare/${song.group_id}`}>
          Compare the takes
        </a>
      )}
      <button type="button" role="menuitem" onClick={() => onEdit(request)}>
        Edit in Create
      </button>
      <button type="button" role="menuitem" disabled={busy} onClick={() => run(() => api.create(request), onRerun)}>
        Render it again
      </button>
      {draft && !finalActive && (
        <button type="button" role="menuitem" disabled={busy} onClick={() => void finalize()}>
          Finalize ({FINAL_STEPS} steps)
        </button>
      )}
      <a role="menuitem" href={api.downloadUrl(song.id, "flac")} download>
        Download FLAC
      </a>
      <a role="menuitem" href={api.downloadUrl(song.id, "wav")} download>
        Download WAV
      </a>
      <button type="button" role="menuitem" aria-expanded={details} onClick={() => setDetails((open) => !open)}>
        {details ? "Hide" : "Show"} settings and lyrics
      </button>
      <hr />
      <button type="button" role="menuitem" className="danger" onClick={() => setConfirming(true)}>
        Delete…
      </button>
    </Menu>
  );

  const title = <SongTitle song={song} onSong={onSong} editing={renaming} onEditingChange={setRenaming} />;
  const player = <SongPlayer track={songTrack(song)} buckets={variant === "take" ? 120 : 160} />;

  return (
    <>
      {variant === "take" ? (
        <>
          <span className="take-name">
            {renaming ? title : name} <span className="muted">seed {request.seed}</span>
          </span>
          {player}
          <div className="row-actions">
            {star}
            {draft && !finalActive && (
              <button type="button" className="finalize" disabled={busy} onClick={() => void finalize()}>
                Finalize
              </button>
            )}
            {finalState}
            {menu}
          </div>
        </>
      ) : (
        <div className="song-row">
          <div className="art" aria-hidden="true" style={artStyle(request.seed)} />
          <div className="row-text">
            <div className="title-line">
              {title}
              {song.source_song_id !== null ? (
                <span className="badge final">Final{draftDeleted ? " of a deleted Draft" : ""}</span>
              ) : draft ? (
                <span className="badge draft">Draft · {request.steps} steps</span>
              ) : (
                <span className="badge final">Full quality</span>
              )}
              {request.abc && <span className="badge">From an edited Score</span>}
            </div>
            <div className="subtitle" title={request.style}>
              {request.style} · {formatDate(song.created_at)}
            </div>
          </div>
          {player}
          <div className="row-actions">
            {star}
            {finalState}
            {menu}
          </div>
        </div>
      )}
      {(details || confirming || actionError) && (
        <div className="song-details" style={variant === "take" ? { flexBasis: "100%", padding: "4px 0 8px" } : undefined}>
          {details && (
            <>
              <dl className="settings">
                <dt>Planning</dt>
                <dd>{MODES[request.mode]}</dd>
                <dt>Quality</dt>
                <dd>{request.steps} steps</dd>
                <dt>Precision</dt>
                <dd>{request.precision}</dd>
                <dt>Seed</dt>
                <dd>{request.seed}</dd>
                <dt>Size</dt>
                <dd>{formatBytes(song.bytes)}</dd>
              </dl>
              {request.lyrics.trim() ? (
                <pre className="lyrics">{request.lyrics}</pre>
              ) : (
                <p className="muted small">No lyrics (instrumental).</p>
              )}
            </>
          )}
          {confirming && (
            <div className="confirm" role="alertdialog" aria-label="Confirm delete" style={{ margin: "8px 0 0" }}>
              <span>Delete “{song.title}” and its files permanently?</span>
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
        </div>
      )}
    </>
  );
}

/** A ⋯ button and its menu; closes on a choice, a click elsewhere or Escape. */
function Menu({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div className="menu-anchor" ref={box}>
      <button
        type="button"
        className="icon-button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        ⋯
      </button>
      {open && (
        <div className="menu" role="menu" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}
