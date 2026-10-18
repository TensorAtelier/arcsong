import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { api, type Job, type Mode, type Precision, type SongRequest } from "./api";
import { DiceIcon } from "./icons";
import { formatEstimate, lengthEstimate, lyricsNotes } from "./lyrics";
import { randomStyle } from "./styles";

type Tab = "write" | "plan" | "cover";

const TABS: { id: Tab; label: string }[] = [
  { id: "write", label: "Write a song" },
  { id: "plan", label: "Plan a melody" },
  { id: "cover", label: "Cover a recording" },
];

const SECTION_TAGS = ["Intro", "Verse", "Pre-Chorus", "Chorus", "Interlude", "Bridge", "Outro"];

/** Sketch renders quick drafts with different seeds; Single renders one Take at full quality. */
type Kind = "sketch" | "single";
const SKETCH_STEPS = 8;
const SINGLE_STEPS = 32;

interface Props {
  onCreated: (job: Job) => void;
  /** Values to start from, e.g. a Library song loaded to tweak. */
  initial?: SongRequest;
  /** False until Setup has installed the model weights. */
  canRender: boolean;
  /** The Cover tab's form. */
  cover: ReactNode;
}

export default function CreateForm({ onCreated, initial, canRender, cover }: Props) {
  const [tab, setTab] = useState<Tab>("write");
  const [kind, setKind] = useState<Kind>(initial && initial.steps === SINGLE_STEPS ? "single" : "sketch");
  const [name, setName] = useState(initial?.title ?? "");
  const [style, setStyle] = useState(initial?.style ?? "");
  const [lyrics, setLyrics] = useState(initial?.lyrics ?? "");
  const [mode, setMode] = useState<Mode>(initial?.mode ?? "full");
  const [seed, setSeed] = useState(initial?.seed != null ? String(initial.seed) : "");
  const [precision, setPrecision] = useState<Precision>(initial?.precision ?? "8bit");
  const [takes, setTakes] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lyricsBox = useRef<HTMLTextAreaElement>(null);

  const seedValue = seed === "" ? null : Number(seed);
  const count = kind === "sketch" ? takes : 1;

  async function run(action: () => Promise<void>) {
    setSubmitting(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (tab === "plan") return void run(planOnly);
    void run(async () => {
      const steps = kind === "sketch" ? SKETCH_STEPS : SINGLE_STEPS;
      const request = { title: name.trim(), style, lyrics, mode, seed: seedValue, precision, steps } as const;
      if (count > 1) (await api.createGroup(request, count)).forEach(onCreated);
      else onCreated(await api.create(request));
    });
  }

  async function planOnly() {
    const job = await api.createScore({
      title: name.trim(),
      style,
      lyrics,
      mode: mode === "off" ? "full" : mode,
      seed: seedValue,
      precision,
      steps: SINGLE_STEPS, // planning ignores it; rendering from the Score keeps this quality
    });
    onCreated(job);
    window.location.hash = `#/score/job/${job.id}`;
  }

  /** Put `[Tag]` on its own line at the cursor, keeping the cursor after it. */
  function insertTag(tag: string) {
    const box = lyricsBox.current;
    const at = box ? box.selectionStart : lyrics.length;
    const before = lyrics.slice(0, at);
    const after = lyrics.slice(at);
    const lead = before === "" || before.endsWith("\n\n") ? "" : before.endsWith("\n") ? "\n" : "\n\n";
    const insert = `${lead}[${tag}]\n`;
    setLyrics(before + insert + after);
    requestAnimationFrame(() => {
      if (!box) return;
      box.focus();
      box.selectionStart = box.selectionEnd = at + insert.length;
    });
  }

  const nameField = (
    <div className="field">
      <label htmlFor="song-name">Song name</label>
      <input
        id="song-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="What is this song called?"
        maxLength={120}
        required
      />
    </div>
  );

  const styleField = (
    <div className="field">
      <label htmlFor="style">Style</label>
      <div className="with-dice">
        <input
          id="style"
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          placeholder="English, indie pop, bright acoustic guitar, warm female vocal"
          required
        />
        <button
          type="button"
          className="dice"
          aria-label="Random style"
          title="Random style"
          onClick={() => setStyle(randomStyle())}
        >
          <DiceIcon />
        </button>
      </div>
    </div>
  );

  const lyricsField = (
    <div className="field">
      <div className="label-row">
        <label htmlFor="lyrics">Lyrics</label>
        <div className="chips" role="group" aria-label="Insert a section tag at the cursor">
          {SECTION_TAGS.map((tag) => (
            <button key={tag} type="button" className="tag" onClick={() => insertTag(tag)}>
              [{tag}]
            </button>
          ))}
        </div>
      </div>
      <textarea
        id="lyrics"
        ref={lyricsBox}
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        rows={tab === "plan" ? 7 : 10}
        placeholder={"[Verse]\nSoft morning light is touching the window\n\n[Chorus]\nStay with the rhythm, let it carry us home"}
      />
      <LyricsHelp lyrics={lyrics} />
    </div>
  );

  const notices = (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!canRender && (
        <p className="notice" role="status">
          The model weights aren’t ready yet. <a href="#/setup">Finish Setup</a> to make songs.
        </p>
      )}
    </>
  );

  return (
    <section className="panel create-main" aria-label="Create">
      <div className="tabs" role="tablist" aria-label="What to make">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "cover" ? (
        <div role="tabpanel" id="panel-cover" aria-labelledby="tab-cover">
          {cover}
        </div>
      ) : (
        <form
          className="form-body"
          role="tabpanel"
          id={`panel-${tab}`}
          aria-labelledby={`tab-${tab}`}
          onSubmit={submit}
        >
          {initial && <p className="muted small">Loaded from the Library. Change anything, then render.</p>}

          {tab === "write" ? (
            <div className="modes" role="radiogroup" aria-label="How to render">
              <button type="button" role="radio" className="mode" aria-checked={kind === "sketch"} onClick={() => setKind("sketch")}>
                <strong>Sketch · {takes} takes</strong>
                <span>Quick drafts with different seeds, side by side. Finalize the one you like.</span>
              </button>
              <button type="button" role="radio" className="mode" aria-checked={kind === "single"} onClick={() => setKind("single")}>
                <strong>Single song</strong>
                <span>One take at full quality, {SINGLE_STEPS} steps. Best once you know the sound.</span>
              </button>
            </div>
          ) : (
            <p className="intro">
              Arcsong writes the melody and chords in a few seconds, as notation you can read, play on a piano and
              edit. Render audio from it when it sounds right.
            </p>
          )}

          {nameField}
          {styleField}
          {lyricsField}

          <div className="seed-row">
            <div className="field">
              <label htmlFor="seed">Seed</label>
              <div className="controls">
                <input
                  id="seed"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))}
                  placeholder="random"
                />
                <button
                  type="button"
                  className="dice"
                  aria-label="New random seed"
                  title="New random seed"
                  onClick={() => setSeed(String(Math.floor(Math.random() * 100000)))}
                >
                  <DiceIcon />
                </button>
              </div>
            </div>
            <details className="advanced" open={initial !== undefined && initial.mode !== "full"}>
              <summary>
                Advanced: {mode === "full" ? "melody + chords" : mode === "melody" ? "melody only" : "no Score"} ·{" "}
                {precision === "8bit" ? "8-bit" : "bf16"}
                {tab === "write" && kind === "sketch" && ` · ${takes} takes`}
              </summary>
              <div className="grid">
                <div>
                  <label htmlFor="mode">Planning</label>
                  <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
                    <option value="full">Melody + chords (recommended)</option>
                    <option value="melody">Melody only</option>
                    {tab === "write" && <option value="off">Off (no Score)</option>}
                  </select>
                </div>
                <div>
                  <label htmlFor="precision">Precision</label>
                  <select id="precision" value={precision} onChange={(e) => setPrecision(e.target.value as Precision)}>
                    <option value="8bit">8-bit (faster)</option>
                    <option value="bf16">bf16</option>
                  </select>
                </div>
                {tab === "write" && kind === "sketch" && (
                  <div>
                    <label htmlFor="takes">Takes in a sketch</label>
                    <select id="takes" value={takes} onChange={(e) => setTakes(Number(e.target.value))}>
                      <option value={2}>2</option>
                      <option value={4}>4</option>
                      <option value={8}>8</option>
                    </select>
                  </div>
                )}
              </div>
              <p className="hint">The same seed, precision and quality reproduce the same song.</p>
            </details>
          </div>

          {notices}

          <div className="cta">
            <button type="submit" className="primary big" disabled={submitting || !name.trim() || !style.trim() || !canRender}>
              {submitting
                ? tab === "plan"
                  ? "Planning…"
                  : "Adding…"
                : tab === "plan"
                  ? "Plan the melody"
                  : kind === "sketch"
                    ? `Sketch ${takes} takes`
                    : "Make the song"}
            </button>
            <span className="muted">
              {tab === "plan"
                ? "A few seconds · no audio yet"
                : kind === "sketch"
                  ? `Quick drafts at ${SKETCH_STEPS} steps${seed !== "" ? `, seeds ${seed}–${Number(seed) + takes - 1}` : ""} · keep writing while they render`
                  : `Full quality at ${SINGLE_STEPS} steps`}
            </span>
          </div>
        </form>
      )}
    </section>
  );
}

const NOTES_SHOWN = 3;

/** The length the lyrics suggest, and what YuE2 is likely to misread. Advice only. */
function LyricsHelp({ lyrics }: { lyrics: string }) {
  const estimate = lengthEstimate(lyrics);
  const notes = lyricsNotes(lyrics);
  return (
    <div className="lyrics-help" aria-live="polite">
      <span className="muted small">
        {estimate
          ? `Song length: ${formatEstimate(estimate)} from these lyrics.`
          : lyrics.trim()
            ? "No sung lines yet: as it stands this is an instrumental, and the model picks its length."
            : "Empty lyrics make an instrumental; the model picks its length."}
      </span>
      {notes.length > 0 && (
        <ul className="lyrics-notes">
          {notes.slice(0, NOTES_SHOWN).map((note) => (
            <li key={`${note.line}-${note.text}`}>
              {note.line !== undefined && <span className="line">Line {note.line}</span>}
              {note.text}
            </li>
          ))}
          {notes.length > NOTES_SHOWN && <li className="more">and {notes.length - NOTES_SHOWN} more</li>}
        </ul>
      )}
    </div>
  );
}
