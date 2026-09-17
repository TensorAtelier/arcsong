import { useCallback, useEffect, useState } from "react";
import { api, type Deleted, type Job, type Song, type SongRequest, watchJobs } from "./api";
import CreateForm from "./CreateForm";
import LibraryView from "./LibraryView";
import QueuePanel from "./QueuePanel";

type View = "create" | "library";

function viewFromHash(): View {
  return window.location.hash === "#/library" ? "library" : "create";
}

export default function App() {
  const [view, setView] = useState<View>(viewFromHash);
  const [jobs, setJobs] = useState<Map<number, Job>>(new Map());
  const [songs, setSongs] = useState<Song[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ request: SongRequest; version: number } | null>(null);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (next: View) => {
    window.location.hash = next === "library" ? "#/library" : "#/";
  };

  const reloadSongs = useCallback(
    () =>
      api
        .songs()
        .then(setSongs)
        .catch((error) => setLoadError(String(error))),
    [],
  );

  // REST responses and SSE messages can arrive out of order; keep the newest snapshot.
  const upsert = useCallback(
    (job: Job) => {
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
        .jobs()
        .then((list) => {
          setLoadError(null);
          setJobs((current) => {
            const next = new Map(list.map((job) => [job.id, job]));
            for (const [id, job] of current) {
              const listed = next.get(id);
              if (listed && listed.seq < job.seq) next.set(id, job);
            }
            return next;
          });
        })
        .catch((error) => setLoadError(String(error)));
    };
    return watchJobs(upsert, removeDeleted, reload);
  }, [upsert, removeDeleted, reloadSongs]);

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
        </nav>
      </header>
      {view === "create" ? (
        <div className="layout">
          <CreateForm
            key={draft?.version ?? 0}
            initial={draft?.request}
            onCreated={upsert}
          />
          <QueuePanel jobs={ordered} onChanged={upsert} error={loadError} />
        </div>
      ) : (
        <LibraryView
          songs={songs}
          error={loadError}
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
