import { type FormEvent, useRef, useState } from "react";
import { api, type Job, type Mode, type Precision } from "./api";
import { formatBytes } from "./format";
import { NoteIcon } from "./icons";

interface Props {
  onCreated: (job: Job) => void;
  /** False until Setup has installed the covers weights and found ffmpeg. */
  ready: boolean;
  /** Its checks are still running, so "not ready" doesn't mean anything yet. */
  checking: boolean;
}

/** Upload a recording, transcribe it into a Score, then re-sing that melody in a new style. */
export default function CoverForm({ onCreated, ready, checking }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [style, setStyle] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [mode, setMode] = useState<Mode>("full");
  const [precision, setPrecision] = useState<Precision>("8bit");
  const [steps, setSteps] = useState<8 | 32>(32);
  const [rights, setRights] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
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

  function pick(files: FileList | null | undefined) {
    const chosen = files?.[0];
    if (chosen) setFile(chosen);
  }

  return (
    <form className="form-body" onSubmit={submit} aria-label="Cover a recording">
      <p className="intro">
        Arcsong transcribes the melody of a recording into a Score, then sings it in your style with your words.
        The recording is read once and deleted as soon as the transcription ends.
      </p>

      <label
        htmlFor="recording"
        className={`drop${over ? " over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          pick(e.dataTransfer.files);
        }}
      >
        <NoteIcon />
        <strong>{file ? file.name : "Drop a recording here, or choose a file"}</strong>
        <span>{file ? `${formatBytes(file.size)} · choose another` : "MP3, WAV, FLAC, M4A or a video"}</span>
        <input
          id="recording"
          ref={picker}
          className="visually-hidden"
          type="file"
          accept="audio/*,video/*"
          onChange={(e) => pick(e.target.files)}
        />
      </label>

      <div className="field">
        <label htmlFor="cover-style">New style</label>
        <input
          id="cover-style"
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          placeholder="English, slow jazz trio, brushed drums, warm male vocal"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="cover-lyrics">Lyrics</label>
        <textarea
          id="cover-lyrics"
          value={lyrics}
          onChange={(e) => setLyrics(e.target.value)}
          rows={6}
          placeholder={"[Verse]\nYour own words for the new version"}
        />
        <span className="muted small">The melody comes from the recording; these words are what gets sung.</span>
      </div>

      <details className="advanced">
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

      <div>
        <label className="check-label">
          <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} /> I have the
          rights to this recording
        </label>
        <p className="hint">
          You are responsible for the rights to anything you upload, and for how you use what comes back.
        </p>
      </div>

      {!ready && checking && (
        <p className="hint" role="status">
          Checking whether covers are ready…
        </p>
      )}
      {!ready && !checking && (
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
      <div className="cta">
        <button
          type="submit"
          className="primary big"
          disabled={submitting || !file || !style.trim() || !rights || !ready || checking}
        >
          {submitting ? "Uploading…" : "Transcribe"}
        </button>
        <span className="muted">Opens the transcribed Score when it is ready</span>
      </div>
    </form>
  );
}
