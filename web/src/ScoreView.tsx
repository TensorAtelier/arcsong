import abcjs from "abcjs";
import { useEffect, useRef, useState } from "react";
import { api, type Job, type ScoreCheck, type SongRequest } from "./api";
import { PauseIcon, PlayIcon } from "./icons";
import { claimAudio, onAudioClaimed } from "./player";
import { formatClock } from "./PlayerUI";

/** The vendored FluidR3 piano (see THIRD_PARTY_NOTICES.md); abcjs appends the instrument file. */
const SOUNDFONT_URL = "/soundfont/";
const CHECK_DELAY = 300;

interface Props {
  source: { kind: "job" | "song"; id: number };
  /** The song's title, as the Library or the queue knows it. */
  title: string | undefined;
  onJob: (job: Job) => void;
}

/** The Score a run planned: notation, a melody preview, and an editor that renders a new song.
 * Editing never writes back — rendering queues a new job from the edited text. */
export default function ScoreView({ source, title, onJob }: Props) {
  const [original, setOriginal] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [request, setRequest] = useState<(SongRequest & { seed: number }) | null>(null);
  const [steps, setSteps] = useState<8 | 32>(32);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [check, setCheck] = useState<ScoreCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // The parsed Score the notation is showing, which MIDI export needs.
  const [tune, setTune] = useState<abcjs.TuneObject | null>(null);

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
        setSteps(loaded.request.steps);
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
      <section className="card score" aria-label="Score">
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
      <section className="card score" aria-label="Score">
        <h2>{title ?? "Score"}</h2>
        {loadError && <p className="error">Could not load this Score: {loadError}</p>}
        {!loadError && (
          <>
            <p className="muted">
              {status === "done"
                ? "This run wrote no Score."
                : status === "failed" || status === "cancelled"
                  ? `This run was ${status} before writing a Score.`
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
  const name = `arcsong-score-${source.kind}-${source.id}`;
  const report = check?.report;
  // The model sometimes plans a take's vocal voice as rests only, lyrics or not: the song then
  // has no sung melody to follow. Count it as a property of this take, not a broken summary.
  const noVocal = report !== null && report !== undefined && report.voices.Vocal.sounding_notes === 0;
  const unsung = noVocal && request !== null && hasSungLyrics(request.lyrics);

  return (
    <section className="score" aria-label="Score">
      <div className="score-head">
        <div>
          <span className="eyebrow">Score</span>
          <h1>{title ?? "Untitled"}</h1>
        </div>
        {report && (
          <div className="facts">
            <span>{report.bpm} BPM</span>
            <span>{formatClock(report.duration_seconds)}</span>
            <span>
              {noVocal ? "no vocal melody" : `${report.voices.Vocal.sounding_notes} vocal notes`} ·{" "}
              {report.voices.Ins.chords || report.voices.Vocal.chords} chords
            </span>
          </div>
        )}
      </div>
      {request && (
        <p className="muted subtitle" title={request.style} style={{ margin: 0 }}>
          {request.style}
        </p>
      )}

      {unsung && (
        <p className="notice" role="note">
          The model planned no vocal melody for this take: the Vocal line is rests from start to end, so the
          lyrics have no notes to be sung on. That comes from the seed, not from your words. Render another
          seed, or write a melody into the Vocal voice in the ABC editor and render from this Score.
        </p>
      )}

      <div className="score-panes">
        <Notation abc={check?.ok === false ? original : text} valid={check?.ok !== false} onTune={setTune} />

        <aside className="card score-side" aria-label="Edit the Score">
          <div className="label-row">
            <label htmlFor="abc">ABC</label>
            <span className={`badge${edited ? " draft" : ""}`}>{edited ? "edited" : "as planned"}</span>
          </div>
          <textarea
            id="abc"
            className="abc"
            value={text}
            spellCheck={false}
            rows={14}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="validity" role="status">
            {check?.ok === false ? (
              <span className="error">{check.error}</span>
            ) : check?.ok ? (
              <>
                <span className="ok">✓ Valid score</span>
                {check.diff &&
                  (check.diff.match ? (
                    <span className="muted">Same melody and meter as the plan.</span>
                  ) : (
                    <>
                      <span className="muted">Changed from the plan:</span>
                      <ul className="diff">
                        {check.diff.differences.map((difference) => (
                          <li key={difference}>{difference}</li>
                        ))}
                      </ul>
                    </>
                  ))}
              </>
            ) : (
              <span className="muted">Checking…</span>
            )}
          </div>
          <div className="actions">
            <button type="button" disabled={busy || !edited} onClick={() => setText(original)}>
              Undo changes
            </button>
            <button
              type="button"
              disabled={busy || check?.ok === false}
              onClick={() => act(() => api.stripChords(text), (result) => setText(result.abc))}
            >
              Strip chords
            </button>
            <button type="button" onClick={() => download(`${name}.abc`, new Blob([text]))}>
              .abc
            </button>
            <button type="button" disabled={check?.ok === false} onClick={() => setActionError(exportMidi(tune, name))}>
              MIDI
            </button>
          </div>
          {request && (
            <div className="render">
              <label htmlFor="quality">Render this Score</label>
              <select id="quality" value={steps} onChange={(e) => setSteps(Number(e.target.value) as 8 | 32)}>
                <option value={8}>Quick draft · 8 steps</option>
                <option value={32}>Full quality · 32 steps</option>
              </select>
              <button
                type="button"
                className="primary big"
                disabled={busy || check?.ok === false}
                onClick={() =>
                  act(
                    () => api.create({ ...request, steps, abc: text, title: title ?? request.title }),
                    (job) => {
                      onJob(job);
                      window.location.hash = "#/";
                    },
                  )
                }
              >
                Render the song
              </button>
              <span className="muted">The Score fixes the melody; the voice and arrangement come from the style.</span>
            </div>
          )}
          {actionError && <p className="error small">{actionError}</p>}
        </aside>
      </div>
    </section>
  );
}

/** Any line that is not empty and not a `[Section]` tag (the rule `db.default_title` uses). */
function hasSungLyrics(lyrics: string): boolean {
  return lyrics.split("\n").some((line) => line.trim() !== "" && !/^\[[^\]]*\]$/.test(line.trim()));
}

function download(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** abcjs turns the Score the view already parsed into a MIDI file, here in the page. */
function exportMidi(tune: abcjs.TuneObject | null, name: string): string | null {
  if (!tune) return "This Score could not be turned into MIDI.";
  try {
    // "binary" hands back the MIDI bytes; "encoded" is a percent-escaped data URI, not base64.
    const bytes = abcjs.synth.getMidiFile(tune, { midiOutputType: "binary" }) as Uint8Array;
    const copy = new Uint8Array(bytes.length);
    copy.set(bytes);  // a plain ArrayBuffer, which Blob's types insist on
    download(`${name}.mid`, new Blob([copy], { type: "audio/midi" }));
    return null;
  } catch (e) {
    return `MIDI export failed: ${e instanceof Error ? e.message : String(e)}`;
  }
}

interface NotationProps {
  abc: string;
  valid: boolean;
  onTune: (tune: abcjs.TuneObject | null) => void;
}

function Notation({ abc, valid, onTune }: NotationProps) {
  const paper = useRef<HTMLDivElement>(null);
  const synth = useRef<InstanceType<typeof abcjs.synth.CreateSynth> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tune, setTune] = useState<abcjs.TuneObject | null>(null);
  const ending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!paper.current) return;
    const [rendered] = abcjs.renderAbc(paper.current, abc, {
      responsive: "resize",
      staffwidth: 740,
      add_classes: true,
    });
    setTune(rendered ?? null);
    onTune(rendered ?? null);
    // An edited Score is a different tune: whatever was primed no longer matches it.
    stop();
  }, [abc, onTune]);

  // Leaving the view must not play on.
  useEffect(() => {
    return () => {
      synth.current?.stop();
      synth.current = null;
      clearTimeout(ending.current);
    };
  }, []);

  // The player bar or a Compare Take starting stops the preview.
  useEffect(
    () =>
      onAudioClaimed("score", () => {
        synth.current?.stop();
        synth.current = null;
        clearTimeout(ending.current);
        setPlaying(false);
      }),
    [],
  );

  function stop() {
    synth.current?.stop();
    synth.current = null;
    clearTimeout(ending.current);
    setPlaying(false);
  }

  async function play() {
    if (playing) return stop();
    if (!tune) return;
    claimAudio("score");
    setPreparing(true);
    setError(null);
    try {
      if (!abcjs.synth.supportsAudio()) throw new Error("This browser can't play audio");
      const created = new abcjs.synth.CreateSynth();
      await created.init({ visualObj: tune, options: { soundFontUrl: SOUNDFONT_URL } });
      const primed = await created.prime();
      synth.current = created;
      created.start();
      setPlaying(true);
      // The synth reports no end of its own, so let the button fall back when it is over.
      ending.current = setTimeout(() => setPlaying(false), (primed.duration + 0.3) * 1000);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(
        message.includes("Can't load sound")
          ? "The preview couldn't load a piano sample; a note may be outside its range (A0–C8)."
          : message,
      );
    } finally {
      setPreparing(false);
    }
  }

  return (
    <section className="notation" aria-label="Notation">
      <div className="player-bar">
        <button type="button" disabled={!tune || preparing} onClick={() => void play()} aria-pressed={playing}>
          <span style={{ width: 12, height: 12, display: "inline-grid" }}>{playing ? <PauseIcon /> : <PlayIcon />}</span>
          {playing ? "Stop" : preparing ? "Loading…" : "Melody on piano"}
        </button>
        {!valid && <span className="muted">Showing the last valid Score.</span>}
        {error && <span className="error small">{error}</span>}
      </div>
      <div ref={paper} className={`paper${valid ? "" : " stale"}`} />
    </section>
  );
}
