import { useEffect, useState } from "react";
import { api, type Job, watchJobs } from "./api";
import CreateForm from "./CreateForm";
import QueuePanel from "./QueuePanel";

export default function App() {
  const [jobs, setJobs] = useState<Map<number, Job>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);

  // REST responses and SSE messages can arrive out of order; keep the newest snapshot.
  const upsert = (job: Job) =>
    setJobs((current) => {
      const known = current.get(job.id);
      if (known && known.seq > job.seq) return current;
      return new Map(current).set(job.id, job);
    });

  useEffect(() => {
    // Load the full list whenever the stream (re)connects: first load, and after a server
    // restart, when jobs may have changed while no events could arrive.
    const reload = () =>
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
    return watchJobs(upsert, reload);
  }, []);

  const ordered = [...jobs.values()].sort((a, b) => b.id - a.id);

  return (
    <main>
      <header>
        <h1>Songloom</h1>
        <p className="muted">Write a style and lyrics; YuE2 makes the song on this Mac.</p>
      </header>
      <div className="layout">
        <CreateForm onCreated={upsert} />
        <QueuePanel jobs={ordered} onChanged={upsert} error={loadError} />
      </div>
    </main>
  );
}
