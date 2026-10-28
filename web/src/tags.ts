/** The style dictionary beside Style: phrases to click into the style, grouped and searchable.
 *
 * YuE2 publishes no tag vocabulary. Its docs say to put "genre, instruments, vocal character,
 * language and tempo" in the style, as comma-separated phrases; its own examples read like
 * "English, warm piano pop, expressive female voice, acoustic piano, … 88 BPM" and, for an
 * instrumental, "Instrumental, … G major, 96 BPM, … no vocals, no singing". This list is
 * hand-picked in that shape: common words the model is likely to know, not a guaranteed set. */

export interface TagGroup {
  name: string;
  tags: string[];
}

export const TAG_GROUPS: TagGroup[] = [
  {
    name: "Language",
    tags: ["English", "Mandarin", "Cantonese", "Japanese", "Korean", "Instrumental"],
  },
  {
    name: "Genre",
    tags: [
      "pop", "piano pop", "indie pop", "dream pop", "synth-pop", "electropop", "city pop", "J-pop", "K-pop",
      "Mandopop", "Cantopop", "rock", "pop rock", "indie rock", "alternative rock", "soft rock", "punk rock",
      "metal", "folk", "indie folk", "chamber folk", "country", "bluegrass", "blues", "jazz", "smooth jazz",
      "jazz ballad", "swing", "bossa nova", "lo-fi hip hop", "lo-fi soul", "hip hop", "trap", "R&B", "neo-soul",
      "soul", "funk", "disco", "house", "deep house", "techno", "drum and bass", "synthwave", "ambient",
      "chillout", "downtempo", "trip hop", "reggae", "latin pop", "reggaeton", "gospel", "musical theatre",
      "cinematic", "orchestral", "classical", "film score", "singer-songwriter", "anime theme", "video game music",
    ],
  },
  {
    name: "Mood",
    tags: [
      "upbeat", "uplifting", "energetic", "happy", "bright", "playful", "romantic", "tender", "warm", "nostalgic",
      "wistful", "melancholic", "sad", "bittersweet", "dreamy", "hazy", "mellow", "chill", "relaxed", "laid-back",
      "calm", "peaceful", "late-night", "smoky", "dark", "moody", "mysterious", "tense", "epic", "anthemic",
      "triumphant", "aggressive", "groovy", "danceable", "sensual",
    ],
  },
  {
    name: "Instruments",
    tags: [
      "acoustic piano", "solo piano", "Rhodes electric piano", "Wurlitzer", "Hammond organ", "synth pads",
      "analog synth bass", "arpeggiated synths", "lead synth", "acoustic guitar", "fingerpicked acoustic guitar",
      "nylon guitar", "clean electric guitar", "distorted guitars", "funky guitar", "slide guitar", "steel guitar",
      "bass guitar", "upright bass", "walking bass", "808 bass", "light drums", "brushed drums", "punchy drums",
      "drum machine", "boom-bap drums", "four-on-the-floor kick", "hand percussion", "congas", "shaker",
      "string quartet", "string ensemble", "violin", "cello", "harp", "brass section", "trumpet", "muted trumpet",
      "saxophone", "flute", "clarinet", "choir", "banjo", "fiddle", "mandolin", "ukulele", "accordion",
      "harmonica", "erhu", "guzheng", "pipa", "koto", "shamisen", "sitar",
    ],
  },
  {
    name: "Voice",
    tags: [
      "male vocal", "female vocal", "soft male vocal", "warm male vocal", "deep male vocal", "raspy male vocal",
      "high tenor vocal", "breathy female vocal", "clear female vocal", "soulful female vocal", "airy female vocal",
      "powerful female vocal", "expressive female voice", "husky voice", "falsetto", "vocal harmonies", "duet",
      "rap vocals", "whispered vocals", "no vocals",
    ],
  },
  {
    name: "Tempo and key",
    tags: [
      "slow tempo", "mid-tempo", "fast tempo", "70 BPM", "80 BPM", "90 BPM", "100 BPM", "110 BPM", "120 BPM",
      "128 BPM", "140 BPM", "C major", "G major", "D major", "F major", "A minor", "E minor", "D minor",
      "3/4 time", "6/8 time", "swing feel", "half-time feel",
    ],
  },
  {
    name: "Sound",
    tags: [
      "lyrical memorable melody", "catchy hook", "unhurried phrasing", "big chorus", "sparse arrangement",
      "lush arrangement", "minimal", "live band", "polished studio production", "lo-fi texture", "vinyl crackle",
      "tape saturation", "vintage recording", "reverb-drenched", "intimate room sound", "natural concert hall acoustics",
      "wide stereo", "short gentle ending", "fade-out ending", "no singing",
    ],
  },
];

/** Letters and digits only, so "lofi" finds "lo-fi" and "rnb" finds "R&B". */
function squash(text: string): string {
  return text.toLowerCase().replace(/&/g, "n").replace(/[^a-z0-9]/g, "");
}

/** The groups with only the tags matching `query` (a group's name matching keeps all of it). */
export function searchTags(query: string, groups: TagGroup[] = TAG_GROUPS): TagGroup[] {
  const needle = squash(query);
  if (!needle) return groups;
  return groups
    .map((group) =>
      squash(group.name).includes(needle) ? group : { ...group, tags: group.tags.filter((tag) => squash(tag).includes(needle)) },
    )
    .filter((group) => group.tags.length > 0);
}

/** The style's phrases, trimmed, empty ones dropped. */
function phrases(style: string): string[] {
  return style
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function hasTag(style: string, tag: string): boolean {
  return phrases(style).some((part) => part.toLowerCase() === tag.toLowerCase());
}

/** Adds the tag at the end of the style, or takes it out if it is already there. */
export function toggleTag(style: string, tag: string): string {
  const parts = phrases(style);
  const kept = parts.filter((part) => part.toLowerCase() !== tag.toLowerCase());
  return (kept.length === parts.length ? [...parts, tag] : kept).join(", ");
}
