/** Help under the Lyrics box: what YuE2 is likely to misread, and roughly how long the song will be.
 *
 * YuE2 reads lyrics as sections: a `[Label]` on its own line, the sung lines under it, a blank line
 * before the next label (its own example: `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`,
 * `[Interlude]`, `[Bridge]`, `[Outro]`). Everything else in the box is sung. */

const LABEL = /^\[([^\]]*)\]$/;
const KNOWN = new Set(["intro", "verse", "pre-chorus", "chorus", "post-chorus", "interlude", "bridge", "hook", "break", "outro"]);
// A whole line in parentheses or asterisks reads like a note to a musician (or an ad-lib).
const DIRECTION = /^\(.*\)$|^\*.*\*$/;
const LONG_LINE = 80;

export interface LyricsNote {
  /** 1-based line number the note is about, when there is one. */
  line?: number;
  text: string;
}

function labelName(line: string): string | null {
  const match = LABEL.exec(line.trim());
  return match ? match[1].trim() : null;
}

/** The section label without a trailing number ("Verse 2" → "verse"). */
function baseName(label: string): string {
  return label.toLowerCase().replace(/\s*\d+$/, "").trim();
}

export function lyricsNotes(lyrics: string): LyricsNote[] {
  const lines = lyrics.split("\n");
  const notes: LyricsNote[] = [];
  if (!lyrics.trim()) return notes; // an instrumental: nothing to check

  const firstLabel = lines.findIndex((line) => labelName(line) !== null);
  if (firstLabel === -1) {
    notes.push({ text: "No section labels: start each part with one, like [Verse] or [Chorus], on its own line." });
  } else {
    const firstText = lines.findIndex((line) => line.trim());
    if (firstText < firstLabel) {
      notes.push({ line: firstText + 1, text: "Lines before the first label: put a label like [Verse] above them." });
    }
  }

  lines.forEach((raw, index) => {
    const line = raw.trim();
    const label = labelName(line);
    if (label !== null) {
      if (index > 0 && lines[index - 1].trim() !== "" && labelName(lines[index - 1]) === null) {
        notes.push({ line: index + 1, text: `Leave a blank line before [${label}].` });
      }
      if (label && !KNOWN.has(baseName(label))) {
        notes.push({ line: index + 1, text: `[${label}] isn't a section YuE2 knows; it may be sung. Try [Verse], [Chorus], [Bridge] or [Interlude].` });
      }
      return;
    }
    if (DIRECTION.test(line)) {
      notes.push({ line: index + 1, text: `"${line}" will be sung as words. If it means an instrumental part, use an empty [Interlude] instead.` });
    } else if (line.length > LONG_LINE) {
      notes.push({ line: index + 1, text: "A long line: split it where you'd take a breath." });
    }
  });
  return notes;
}

/** Sung lines: not blank, not a label. */
export function sungLines(lyrics: string): number {
  return lyrics.split("\n").filter((line) => line.trim() && labelName(line) === null).length;
}

/** A rough song length from the lyrics, as a range. Fitted on real renders (2026-10-17: 4 sung
 * lines → 45–71 s, 28 → 165 s, 39 → 189 s): about 40 s plus 3.8 s a sung line, ±25%. Null for an
 * instrumental, whose length the model picks. */
export function lengthEstimate(lyrics: string): { low: number; high: number } | null {
  const sung = sungLines(lyrics);
  if (sung === 0) return null;
  const seconds = 40 + 3.8 * sung;
  return { low: seconds * 0.8, high: seconds * 1.25 };
}

/** "about 45–70 s" for short songs, "about 2–3½ min" for longer ones (bounds rounded outward). */
export function formatEstimate({ low, high }: { low: number; high: number }): string {
  if (high < 120) {
    return `about ${Math.floor(low / 5) * 5}–${Math.ceil(high / 5) * 5} s`;
  }
  const show = (minutes: number) => (minutes % 1 ? `${Math.floor(minutes) || ""}½` : String(minutes));
  const low2 = Math.floor(low / 30) / 2;
  const high2 = Math.ceil(high / 30) / 2;
  return `about ${show(low2)}–${show(high2)} min`;
}
