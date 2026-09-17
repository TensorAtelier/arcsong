import abcjs from "abcjs";
import { useEffect, useRef, useState } from "react";
import { api, type Job, type ScoreCheck, type SongRequest } from "./api";

/** The vendored FluidR3 piano (see THIRD_PARTY_NOTICES.md); abcjs appends the instrument file. */
const SOUNDFONT_URL = "/soundfont/";
const CHECK_DELAY = 300;

interface Props {
  source: { kind: "job" | "song"; id: number };
  onJob: (job: Job) => void;
}

/** The Score a run planned: notation, a melody preview, and an editor that renders a new song.
 * Editing never writes back — rendering queues a new job from the edited text. */
export default function ScoreView({ source, onJob }: Props) {
  const [original, setOriginal] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [request, setRequest] = useState<(SongRequest & { seed: number }) | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [check, setCheck] = useState<ScoreCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Bumped to reload while the run is still planning.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    const load =
      source.kind === "job"
        ? api.score(source.id).then((score) => ({
            abc: score.abc,
            request: score.job.request,
            status: score.job.status,
            error: score.job.error,
          }))
        : api.songScore(source.id).then((score) => ({
            abc: score.abc,
            request: score.request,
            status: "done",
            error: null,
          }));
    load
      .then((loaded) => {
        if (cancelled) return;
        setLoaded(true);
        setStatus(loaded.status);
        setJobError(loaded.error);
        setRequest(loaded.request);
        setOriginal((current) => {
          // Only the first Score to arrive seeds the editor; a reload must not undo edits.
          if (!current && loaded.abc) setText(loaded.abc);
          return current || (loaded.abc ?? "");
        });
      })
      .catch((error) => !cancelled && setLoadError(String(error)));
    return () => {
      cancelled = true;
    };
  }, [source.kind, source.id, attempt]);

  // A Score job opened from Create is usually still running; watch for its Score, and only
  // while it can still produce one — never after an error or a finished job.
  useEffect(() => {
    const planning = status === "queued" || status === "running";
    if (original || loadError !== null || source.kind !== "job" || !planning) return;
    const timer = setTimeout(() => setAttempt((n) => n + 1), 1000);
    return () => clearTimeout(timer);
  }, [original, loadError, status, source.kind, attempt]);

  // Validate as the user types, against the Score this one started from.
  useEffect(() => {
    if (original === null || !text.trim()) return;
    let current = true;  // a slower earlier answer must not overwrite a newer one
    const timer = setTimeout(() => {
      api
        .checkScore(text, original)
        .then((result) => current && setCheck(result))
        .catch(
          (error) =>
            current && setCheck({ ok: false, error: String(error), report: null, diff: null }),
        );
    }, CHECK_DELAY);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [text, original]);

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

  if (!loaded && loadError === null) {
    return (
      <section className="panel score" aria-label="Score">
        <h2>Score</h2>
        {loadError ? (
          <p className="error">Could not load this Score: {loadError}</p>
        ) : (
          <p className="muted">Loading…</p>
        )}
      </section>
    );
  }

  if (!original || loadError !== null) {
    return (
      <section className="panel score" aria-label="Score">
        <h2>Score</h2>
        {loadError && <p className="error">Could not load this Score: {loadError}</p>}
        {!loadError && (
          <>
            <p className="muted">
              {status === "done"
                ? "This run wrote no Score."
                : status === "failed" || status === "cancelled"
                  ? `This run ${status} before writing a Score.`
                  : "Writing the Score… this page updates when it is ready."}{" "}
              <a href="#/">Back to Create</a>
            </p>
            {jobError && (
              <details className="error-details">
                <summary>{jobError.trim().split("\n").pop()}</summary>
                <pre>{jobError}</pre>
              </details>
            )}
          </>
        )}
      </section>
    );
  }

  const edited = text !== original;

  return (
    <section className="panel score" aria-label="Score">
      <div className="library-head">
        <h2>Score</h2>
        {check?.report && (
          <p className="muted small">
            {check.report.bpm} BPM · {Math.round(check.report.duration_seconds)} s ·{" "}
            {check.report.voices.Vocal.sounding_notes} vocal notes ·{" "}
            {check.report.voices.Vocal.chords} chords
          </p>
        )}
      </div>
      {request && (
        <p className="compare-style" title={request.style}>
          {request.style}
        </p>
      )}

      <Notation abc={check?.ok === false ? original : text} valid={check?.ok !== false} />

      <div className="score-panes">
        <div>
          <div className="label-row">
            <label htmlFor="abc">ABC</label>
            <span className="muted small">{edited ? "edited" : "as planned"}</span>
          </div>
          <textarea
            id="abc"
            className="abc"
            value={text}
            spellCheck={false}
            rows={14}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="score-side">
          {check?.ok === false && (
            <p className="error small" role="alert">
              {check.error}
            </p>
          )}
          {check?.ok && check.diff && (
            <p className="small">
              {check.diff.match ? (
                <span className="muted">Same melody and meter as the original.</span>
              ) : (
                <>
                  <strong>Changed:</strong>
                  <ul className="diff">
                    {check.diff.differences.map((difference) => (
                      <li key={difference}>{difference}</li>
                    ))}
                  </ul>
                </>
              )}
            </p>
          )}
          <div className="actions">
            <button
              type="button"
              disabled={busy || check?.ok === false}
              onClick={() => act(() => api.stripChords(text), (result) => setText(result.abc))}
            >
              Remove chords
            </button>
            <button type="button" disabled={busy || !edited} onClick={() => setText(original)}>
              Reset
            </button>
            {request && (
              <button
                type="button"
                className="primary"
                disabled={busy || check?.ok === false}
                onClick={() =>
                  act(
                    () => api.create({ ...request, abc: text }),
                    (job) => {
                      onJob(job);
                      window.location.hash = "#/";
                    },
                  )
                }
              >
                Render song from this Score
              </button>
            )}
          </div>
          {actionError && <p className="error small">{actionError}</p>}
        </div>
      </div>
    </section>
  );
}

function Notation({ abc, valid }: { abc: string; valid: boolean }) {
  const paper = useRef<HTMLDivElement>(null);
  const synth = useRef<InstanceType<typeof abcjs.synth.CreateSynth> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tune, setTune] = useState<abcjs.TuneObject | null>(null);

  useEffect(() => {
    if (!paper.current) return;
    const [rendered] = abcjs.renderAbc(paper.current, abc, {
      responsive: "resize",
      staffwidth: 740,
      add_classes: true,
    });
    setTune(rendered ?? null);
  }, [abc]);

  // A new Score invalidates whatever was primed, and leaving the view must not play on.
  useEffect(() => {
    return () => {
      synth.current?.stop();
      synth.current = null;
    };
  }, [tune]);

  function stop() {
    synth.current?.stop();
    setPlaying(false);
  }

  async function play() {
    if (playing) return stop();
    if (!tune) return;
    setPreparing(true);
    setError(null);
    try {
      if (!abcjs.synth.supportsAudio()) throw new Error("This browser can't play audio");
      const created = new abcjs.synth.CreateSynth();
      await created.init({ visualObj: tune, options: { soundFontUrl: SOUNDFONT_URL } });
      await created.prime();
      synth.current = created;
      created.start();
      setPlaying(true);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(
        message.includes("Can't load sound")
          ? "This Score has a note outside the piano the preview uses (A0–C8)."
          : message,
      );
    } finally {
      setPreparing(false);
    }
  }

  return (
    <div className="notation">
      <div ref={paper} className={`paper${valid ? "" : " stale"}`} aria-label="Notation" />
      <div className="player-bar">
        <button type="button" disabled={!tune || preparing} onClick={() => void play()}>
          {playing ? "❚❚ Stop" : preparing ? "Loading…" : "▶ Play melody"}
        </button>
        {!valid && <span className="muted small">Showing the last valid Score.</span>}
        {error && <span className="error small">{error}</span>}
      </div>
    </div>
  );
}
