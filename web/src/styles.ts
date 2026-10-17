/** Random styles for the dice beside Style: tag form, comma-separated, the shape YuE2 was trained
 * on ("City Pop, upbeat, danceable, groovy bass, …"). Each genre carries instruments and moods
 * that belong with it, so a roll reads like a song rather than a pile of words. */

interface Genre {
  name: string;
  moods: string[];
  instruments: string[];
}

const GENRES: Genre[] = [
  { name: "lo-fi soul", moods: ["late-night", "mellow", "warm"], instruments: ["warm Rhodes", "brushed drums", "upright bass", "muted guitar"] },
  { name: "city pop", moods: ["upbeat", "groovy", "neon city night"], instruments: ["groovy electric bass", "bright synth stabs", "funky guitar", "tight drums"] },
  { name: "indie folk", moods: ["gentle", "intimate", "wistful"], instruments: ["fingerpicked acoustic guitar", "soft piano", "light percussion", "cello"] },
  { name: "dream pop", moods: ["hazy", "floating", "slow tempo"], instruments: ["reverb guitars", "airy synth pads", "soft drum machine", "shimmering keys"] },
  { name: "synthwave", moods: ["driving", "nostalgic", "retro"], instruments: ["analog synth bass", "gated drums", "arpeggiated synths", "bright lead synth"] },
  { name: "jazz ballad", moods: ["smoky", "tender", "slow"], instruments: ["piano trio", "brushed snare", "walking bass", "muted trumpet"] },
  { name: "pop rock", moods: ["anthemic", "energetic", "uplifting"], instruments: ["electric guitars", "punchy drums", "bass guitar", "big chorus"] },
  { name: "bossa nova", moods: ["breezy", "relaxed", "sunny"], instruments: ["nylon guitar", "soft shaker", "upright bass", "light flute"] },
  { name: "R&B", moods: ["smooth", "sultry", "laid-back"], instruments: ["electric piano", "deep bass", "crisp hi-hats", "soft synth pads"] },
  { name: "country", moods: ["heartfelt", "open-road", "warm"], instruments: ["steel guitar", "acoustic guitar", "fiddle", "steady drums"] },
  { name: "electropop", moods: ["danceable", "bright", "catchy"], instruments: ["four-on-the-floor kick", "plucky synths", "sidechained pads", "synth bass"] },
  { name: "chamber folk", moods: ["melancholic", "delicate", "autumnal"], instruments: ["string quartet", "acoustic guitar", "harp", "piano"] },
];

const VOICES = [
  "soft male vocal",
  "warm male vocal",
  "raspy male vocal",
  "breathy female vocal",
  "clear female vocal",
  "soulful female vocal",
  "airy female vocal",
  "deep male vocal",
];

function pick<T>(items: T[], random: () => number): T {
  return items[Math.floor(random() * items.length)];
}

function pickTwo<T>(items: T[], random: () => number): [T, T] {
  const first = Math.floor(random() * items.length);
  const second = (first + 1 + Math.floor(random() * (items.length - 1))) % items.length;
  return [items[first], items[second]];
}

/** e.g. "English, city pop, upbeat, groovy electric bass, funky guitar, clear female vocal" */
export function randomStyle(random: () => number = Math.random): string {
  const genre = pick(GENRES, random);
  const [first, second] = pickTwo(genre.instruments, random);
  return ["English", genre.name, pick(genre.moods, random), first, second, pick(VOICES, random)].join(", ");
}
