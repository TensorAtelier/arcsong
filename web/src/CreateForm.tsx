import { type FormEvent, useState } from "react";
import { api, type Job, type Mode, type Precision } from "./api";

const LYRICS_TEMPLATE = `[Verse]


[Chorus]


[Verse]


[Chorus]
`;

interface Props {
  onCreated: (job: Job) => void;
}

export default function CreateForm({ onCreated }: Props) {
  const [style, setStyle] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [mode, setMode] = useState<Mode>("full");
  const [seed, setSeed] = useState("");
  const [precision, setPrecision] = useState<Precision>("8bit");
  const [steps, setSteps] = useState<8 | 32>(32);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.create({
        style,
        lyrics,
        mode,
        seed: seed === "" ? null : Number(seed),
        precision,
        steps,
      });
      onCreated(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="Create a song">
      <h2>Create</h2>

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

      <details>
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

      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" className="primary" disabled={submitting || !style.trim()}>
        {submitting ? "Adding…" : "Generate"}
      </button>
    </form>
  );
}
