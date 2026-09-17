import { type FormEvent, useState } from "react";
import { api, type Job, type Mode, type Precision, type SongRequest } from "./api";

const LYRICS_TEMPLATE = `[Verse]


[Chorus]


[Verse]


[Chorus]
`;

interface Props {
  onCreated: (job: Job) => void;
  /** Values to start from, e.g. a Library song loaded to tweak. */
  initial?: SongRequest;
  /** False until Setup has installed the model weights. */
  canRender: boolean;
}

export default function CreateForm({ onCreated, initial, canRender }: Props) {
  const [style, setStyle] = useState(initial?.style ?? "");
  const [lyrics, setLyrics] = useState(initial?.lyrics ?? "");
  const [mode, setMode] = useState<Mode>(initial?.mode ?? "full");
  const [seed, setSeed] = useState(initial?.seed != null ? String(initial.seed) : "");
  const [precision, setPrecision] = useState<Precision>(initial?.precision ?? "8bit");
  const [steps, setSteps] = useState<8 | 32>(initial?.steps ?? 32);
  const [takes, setTakes] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const request = { style, lyrics, mode, seed: seed === "" ? null : Number(seed), precision, steps };
      if (takes > 1) {
        (await api.createGroup(request, takes)).forEach(onCreated);
      } else {
        onCreated(await api.create(request));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function planOnly() {
    setPlanning(true);
    setError(null);
    try {
      const job = await api.createScore({
        style,
        lyrics,
        mode: mode === "off" ? "full" : mode,
        seed: seed === "" ? null : Number(seed),
        precision,
      });
      onCreated(job);
      window.location.hash = `#/score/job/${job.id}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPlanning(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="Create a song">
      <h2>Create</h2>
      {initial && <p className="hint">Loaded from the Library. Change anything, then Generate.</p>}

      <label htmlFor="style">Style</label>
      <input
        id="style"
        value={style}
        onChange={(e) => setStyle(e.target.value)}
        placeholder="English, indie pop, bright acoustic guitar, warm female vocal"
        required
      />

      <div className="label-row">
        <label htmlFor="lyrics">Lyrics</label>
        <button
          type="button"
          className="link"
          onClick={() => setLyrics((text) => (text.trim() ? `${text}\n\n${LYRICS_TEMPLATE}` : LYRICS_TEMPLATE))}
        >
          Insert section tags
        </button>
      </div>
      <textarea
        id="lyrics"
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        rows={12}
        placeholder={"[Verse]\nSoft morning light is touching the window\n\n[Chorus]\nStay with the rhythm, let it carry us home"}
      />
      <p className="hint">Section tags like [Verse] and [Chorus] shape the song. Leave empty for an instrumental.</p>

      <details open={initial !== undefined}>
        <summary>Advanced</summary>
        <div className="grid">
          <div>
            <label htmlFor="mode">Planning</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              <option value="full">Melody + chords (recommended)</option>
              <option value="melody">Melody only</option>
              <option value="off">Off (no Score)</option>
            </select>
          </div>
          <div>
            <label htmlFor="steps">Quality</label>
            <select id="steps" value={steps} onChange={(e) => setSteps(Number(e.target.value) as 8 | 32)}>
              <option value={32}>Standard (32 steps)</option>
              <option value={8}>Quick draft (8 steps)</option>
            </select>
          </div>
          <div>
            <label htmlFor="precision">Precision</label>
            <select id="precision" value={precision} onChange={(e) => setPrecision(e.target.value as Precision)}>
              <option value="8bit">8-bit (faster)</option>
              <option value="bf16">bf16</option>
            </select>
          </div>
          <div>
            <label htmlFor="seed">Seed</label>
            <input
              id="seed"
              inputMode="numeric"
              pattern="[0-9]*"
              value={seed}
              onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))}
              placeholder="random"
            />
          </div>
        </div>
        <p className="hint">The same seed, precision and quality reproduce the same song.</p>
      </details>

      <div className="takes-row">
        <label htmlFor="takes">Takes</label>
        <select id="takes" value={takes} onChange={(e) => setTakes(Number(e.target.value))}>
          <option value={1}>1</option>
          <option value={2}>2 variations</option>
          <option value={4}>4 variations</option>
          <option value={8}>8 variations</option>
        </select>
      </div>
      {takes > 1 && (
        <p className="hint">
          {takes} Takes with different seeds{seed !== "" && ` (${seed}, ${Number(seed) + 1}, …)`}, compared side by side.
          {steps === 32
            ? " Quick draft (8 steps) under Advanced makes them much faster; Finalize the one you like."
            : " Finalize the one you like at full quality."}
        </p>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {!canRender && (
        <p className="notice" role="status">
          The model weights aren’t ready yet. <a href="#/setup">Finish Setup</a> to make songs.
        </p>
      )}
      <button type="submit" className="primary" disabled={submitting || !style.trim() || !canRender}>
        {submitting ? "Adding…" : takes > 1 ? `Generate ×${takes}` : "Generate"}
      </button>
      <button
        type="button"
        disabled={submitting || planning || !style.trim() || !canRender}
        onClick={() => void planOnly()}
      >
        {planning ? "Planning…" : "Score only"}
      </button>
      <p className="hint">
        Score only writes the melody in seconds, to read, edit and render from — no audio yet.
      </p>
    </form>
  );
}
