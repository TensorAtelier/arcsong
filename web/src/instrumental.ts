/** How an instrumental Score is rendered, following YuE2's own instrumental workflow: the style
 * starts with "Instrumental" and rules out singing, and the lyrics keep only section labels. */

const VOCAL_PHRASE = /\b(vocals?|voices?|singers?|singing|sung|choir|rap|duet|falsetto|harmonies)\b/i;
const NO_SINGING = ["no vocals", "no singing"];

export function instrumentalStyle(style: string): string {
  const phrases = style
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part && !VOCAL_PHRASE.test(part) && part.toLowerCase() !== "instrumental");
  return ["Instrumental", ...phrases, ...NO_SINGING].join(", ");
}

/** The lyrics' `[Section]` labels, one per paragraph; empty if there are none. */
export function instrumentalLyrics(lyrics: string): string {
  return lyrics
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^\[[^\]]*\]$/.test(line))
    .join("\n\n");
}

export function instrumentalTitle(title: string): string {
  return /instrumental/i.test(title) ? title : `${title} (instrumental)`;
}
