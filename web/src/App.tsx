import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Deleted, type Job, type Setup, type Song, type SongRequest, watchEvents } from "./api";
import CompareView from "./CompareView";
import ScoreView from "./ScoreView";
import CreateForm from "./CreateForm";
import LibraryView from "./LibraryView";
import QueuePanel from "./QueuePanel";
import SetupView from "./SetupView";

type View = "create" | "library" | "setup" | "compare" | "score";

const HASHES: Record<View, string> = {
  create: "#/",
  library: "#/library",
  setup: "#/setup",
  compare: "#/compare/",
  score: "#/score/",
};

function viewFromHash(): View {
  const hash = window.location.hash;
  if (scoreSource(hash) !== null) return "score";
  if (compareGroup(hash) !== null) return "compare";
  return hash === HASHES.library ? "library" : hash === HASHES.setup ? "setup" : "create";
}

/** The Score behind `#/score/job/<id>` or `#/score/song/<id>`, or null. */
function scoreSource(hash: string): { kind: "job" | "song"; id: number } | null {
  const match = /^#\/score\/(job|song)\/(\d+)$/.exec(hash);
  return match ? { kind: match[1] as "job" | "song", id: Number(match[2]) } : null;
}

/** The group id in `#/compare/<id>`, or null. */
function compareGroup(hash: string): number | null {
  const match = /^#\/compare\/(\d+)$/.exec(hash);
  return match ? Number(match[1]) : null;
}

export default function App() {
  const [view, setView] = useState<View>(viewFromHash);
  const [groupId, setGroupId] = useState<number | null>(() => compareGroup(window.location.hash));
  const [score, setScore] = useState(() => scoreSource(window.location.hash));
  const [jobs, setJobs] = useState<Map<number, Job>>(new Map());
  const [songs, setSongs] = useState<Song[] | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [songsError, setSongsError] = useState<string | null>(null);
  // Deleted ids, remembered so a list request already in flight when a delete lands can't
  // bring the song or its job back.
  const deletedJobs = useRef(new Set<number>());
  const deletedSongs = useRef(new Set<number>());
  const [draft, setDraft] = useState<{ request: SongRequest; version: number } | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  // Only the first Setup load may send the page to Setup, so a user who navigates away stays.
  const routedToSetup = useRef(false);

  useEffect(() => {
    const onHash = () => {
      setView(viewFromHash());
      setGroupId(compareGroup(window.location.hash));
      setScore(scoreSource(window.location.hash));
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (next: View) => {
    window.location.hash = HASHES[next];
  };

  // REST responses and SSE messages can arrive out of order; keep the newest snapshot.
  const updateSetup = useCallback((next: Setup) => {
    setSetup((current) => (current && current.seq > next.seq ? current : next));
    if (!routedToSetup.current) {
      routedToSetup.current = true;
      const hash = window.location.hash;
      if (!next.ready && (hash === "" || hash === "#" || hash === HASHES.create)) {
        window.location.hash = HASHES.setup;
      }
    }
  }, []);

  const reloadSongs = useCallback(
    () =>
      api
        .songs()
        .then((list) => {
          setSongsError(null);
          setSongs(list.filter((song) => !deletedSongs.current.has(song.id)));
        })
        .catch((error) => setSongsError(String(error))),
    [],
  );

  // Job snapshots, like Setup's, keep the newest.
  const upsert = useCallback(
    (job: Job) => {
      if (deletedJobs.current.has(job.id)) return;
      setJobs((current) => {
        const known = current.get(job.id);
        if (known && known.seq > job.seq) return current;
        if (job.status === "done" && known?.status !== "done") void reloadSongs();
        return new Map(current).set(job.id, job);
      });
    },
    [reloadSongs],
  );

  // Song messages carry the song without its size; keep the size the list already has.
  const updateSong = useCallback((song: Song) => {
    if (deletedSongs.current.has(song.id)) return;
    setSongs((current) => current && current.map((s) => (s.id === song.id ? { ...s, ...song, bytes: s.bytes } : s)));
    setJobs((current) => {
      const job = current.get(song.job_id);
      return job ? new Map(current).set(job.id, { ...job, starred: song.starred }) : current;
    });
  }, []);

  const removeDeleted = useCallback((deleted: Deleted) => {
    deletedJobs.current.add(deleted.job_id);
    deletedSongs.current.add(deleted.song_id);
    setJobs((current) => {
      if (!current.has(deleted.job_id)) return current;
      const next = new Map(current);
      next.delete(deleted.job_id);
      return next;
    });
    setSongs((current) => current && current.filter((song) => song.id !== deleted.song_id));
  }, []);

  useEffect(() => {
    // Load everything whenever the stream (re)connects: first load, and after a server
    // restart, when jobs and songs may have changed while no events could arrive.
    const reload = () => {
      void reloadSongs();
      api
        .setup()
        .then((next) => {
          setSetupError(null);
          updateSetup(next);
        })
        .catch((error) => setSetupError(String(error)));
      api
        .jobs()
        .then((list) => {
          setJobsError(null);
          setJobs((current) => {
            const kept = list.filter((job) => !deletedJobs.current.has(job.id));
            const next = new Map(kept.map((job) => [job.id, job]));
            for (const [id, job] of current) {
              const listed = next.get(id);
              if (listed && listed.seq < job.seq) next.set(id, job);
            }
            return next;
          });
        })
        .catch((error) => setJobsError(String(error)));
    };
    return watchEvents({
      onJob: upsert,
      onDeleted: removeDeleted,
      onSetup: updateSetup,
      onSong: updateSong,
      onConnect: reload,
    });
  }, [upsert, removeDeleted, reloadSongs, updateSetup, updateSong]);

  const ordered = [...jobs.values()].sort((a, b) => b.id - a.id);

  return (
    <main>
      <header className="top">
        <div>
          <h1>Songloom</h1>
          <p className="muted">Write a style and lyrics; YuE2 makes the song on this Mac.</p>
        </div>
        <nav aria-label="Views">
          <a href="#/" aria-current={view === "create" ? "page" : undefined}>
            Create
          </a>
          <a href="#/library" aria-current={view === "library" ? "page" : undefined}>
            Library{songs ? ` (${songs.length})` : ""}
          </a>
          <a href="#/setup" aria-current={view === "setup" ? "page" : undefined}>
            Setup
            {setup && !setup.ready && (
              <span className="attention" aria-label="needs attention">
                {" "}
                !
              </span>
            )}
          </a>
        </nav>
      </header>
      {view === "setup" ? (
        <SetupView setup={setup} error={setupError} onChanged={updateSetup} />
      ) : view === "score" && score !== null ? (
        <ScoreView source={score} onJob={upsert} />
      ) : view === "compare" && groupId !== null ? (
        <CompareView groupId={groupId} jobs={ordered} songs={songs} onJob={upsert} onSong={updateSong} />
      ) : view === "create" ? (
        <div className="layout">
          <CreateForm
            key={draft?.version ?? 0}
            initial={draft?.request}
            onCreated={upsert}
            canRender={setup?.can_render ?? true}
          />
          <QueuePanel jobs={ordered} onChanged={upsert} error={jobsError} />
        </div>
      ) : (
        <LibraryView
          songs={songs}
          jobs={ordered}
          onJob={upsert}
          onSong={updateSong}
          error={songsError}
          onDeleted={removeDeleted}
          onRerun={(job) => {
            upsert(job);
            go("create");
          }}
          onEdit={(request) => {
            setDraft((current) => ({ request, version: (current?.version ?? 0) + 1 }));
            go("create");
          }}
        />
      )}
    </main>
  );
}
