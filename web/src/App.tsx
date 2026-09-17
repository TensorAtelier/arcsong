import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Deleted, type Job, type Setup, type Song, type SongRequest, watchJobs } from "./api";
import CreateForm from "./CreateForm";
import LibraryView from "./LibraryView";
import QueuePanel from "./QueuePanel";
import SetupView from "./SetupView";

type View = "create" | "library" | "setup";

const HASHES: Record<View, string> = { create: "#/", library: "#/library", setup: "#/setup" };

function viewFromHash(): View {
  const hash = window.location.hash;
  return hash === HASHES.library ? "library" : hash === HASHES.setup ? "setup" : "create";
}

export default function App() {
  const [view, setView] = useState<View>(viewFromHash);
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
    const onHash = () => setView(viewFromHash());
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
    return watchJobs(upsert, removeDeleted, updateSetup, reload);
  }, [upsert, removeDeleted, reloadSongs, updateSetup]);

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
