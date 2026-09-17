import { type FormEvent, useRef, useState } from "react";
import { api, type Job, type Mode, type Precision } from "./api";
import { formatBytes } from "./format";

interface Props {
  onCreated: (job: Job) => void;
  /** False until Setup has installed the covers weights and found ffmpeg. */
  ready: boolean;
}

/** Upload a recording, transcribe it into a Score, then re-sing that melody in a new style. */
export default function CoverForm({ onCreated, ready }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [style, setStyle] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [mode, setMode] = useState<Mode>("full");
  const [precision, setPrecision] = useState<Precision>("8bit");
  const [steps, setSteps] = useState<8 | 32>(32);
  const [rights, setRights] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.createCover({
        audio: file,
        style,
        lyrics,
        mode: mode === "off" ? "full" : mode,
        precision,
        steps,
        rights_confirmed: rights,
      });
      onCreated(job);
      window.location.hash = `#/score/job/${job.id}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="Cover a recording">
      <h2>Cover</h2>
      <p className="hint">
        Transcribe a recording into a Score, then re-sing that melody in a style of your own. The
        recording is read once and deleted as soon as the transcription ends.
      </p>

      <label htmlFor="recording">Recording</label>
      <input
        id="recording"
        ref={picker}
        type="file"
        accept="audio/*,video/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      {file && (
        <p className="hint">
          {file.name} · {formatBytes(file.size)}
        </p>
      )}

      <label htmlFor="cover-style">New style</label>
      <input
        id="cover-style"
        value={style}
        onChange={(e) => setStyle(e.target.value)}
        placeholder="English, slow jazz trio, brushed drums, warm male vocal"
        required
      />

      <label htmlFor="cover-lyrics">Lyrics</label>
      <textarea
        id="cover-lyrics"
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        rows={6}
        placeholder={"[Verse]\nYour own words for the new version"}
      />
      <p className="hint">The melody comes from the recording; these words are what gets sung.</p>

      <details>
        <summary>Advanced</summary>
        <div className="grid">
          <div>
            <label htmlFor="cover-mode">Planning</label>
            <select id="cover-mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              <option value="full">Melody + chords</option>
              <option value="melody">Melody only</option>
            </select>
          </div>
          <div>
            <label htmlFor="cover-steps">Quality</label>
            <select
              id="cover-steps"
              value={steps}
              onChange={(e) => setSteps(Number(e.target.value) as 8 | 32)}
            >
              <option value={32}>Standard (32 steps)</option>
              <option value={8}>Quick draft (8 steps)</option>
            </select>
          </div>
          <div>
            <label htmlFor="cover-precision">Precision</label>
            <select
              id="cover-precision"
              value={precision}
              onChange={(e) => setPrecision(e.target.value as Precision)}
            >
              <option value="8bit">8-bit (faster)</option>
              <option value="bf16">bf16</option>
            </select>
          </div>
        </div>
      </details>

      <label className="check-label">
        <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} /> I have
        the rights to this recording
      </label>
      <p className="hint">
        You are responsible for the rights to anything you upload, and for how you use what comes back.
      </p>

      {!ready && (
        <p className="notice" role="status">
          Covers need ffmpeg and the transcription weights. <a href="#/setup">Finish Setup</a> to use
          them.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        className="primary"
        disabled={submitting || !file || !style.trim() || !rights || !ready}
      >
        {submitting ? "Uploading…" : "Transcribe"}
      </button>
    </form>
  );
}
