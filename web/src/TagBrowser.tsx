import { useState } from "react";
import { hasTag, searchTags } from "./tags";

/** The style dictionary: search, then click a phrase to add it to Style (or take it out). */
export default function TagBrowser({ style, onToggle }: { style: string; onToggle: (tag: string) => void }) {
  const [query, setQuery] = useState("");
  const groups = searchTags(query);
  return (
    <div className="tag-browser" id="tag-browser">
      <input
        type="search"
        aria-label="Search styles"
        placeholder="Search: jazz, piano, lofi, 90 BPM…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      <div className="tag-groups">
        {groups.length === 0 && (
          <p className="muted small">Nothing matches. You can still type any phrase into Style.</p>
        )}
        {groups.map((group) => (
          <section key={group.name} aria-label={group.name}>
            <h4>{group.name}</h4>
            <div className="chips">
              {group.tags.map((tag) => {
                const on = hasTag(style, tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    className="style-tag"
                    aria-pressed={on}
                    onClick={() => onToggle(tag)}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>
      <p className="muted small">A starting list, not a fixed vocabulary: any short phrase works.</p>
    </div>
  );
}
