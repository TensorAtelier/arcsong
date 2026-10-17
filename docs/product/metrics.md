# Metrics

Arcsong has no telemetry, by charter. Everything here is public repository data.

Take a snapshot with `uv run python scripts/metrics.py --note "…"` (needs `gh` with push access):
it reads all three sources below and writes today's row, replacing it on a rerun.

## Sources

### github-repo

- Measures: stars, forks, watchers, open issues (and how many from people other than the owner).
- Read with: `gh api repos/TensorAtelier/arcsong --jq '{stars:.stargazers_count,forks:.forks_count,watchers:.subscribers_count,issues:.open_issues_count}'`
- Lag: live.

### github-traffic

- Measures: page views and clones, total and unique, over the last 14 days. CI checkouts count as
  clones, so read uniques, and compare against the CI run count for the same window.
- Read with: `gh api repos/TensorAtelier/arcsong/traffic/views --jq '{count,uniques}'` and
  `.../traffic/clones`; referrers: `.../traffic/popular/referrers`. Needs push access (the
  owner's `gh` login has it).
- Lag: about a day; GitHub keeps only 14 days, so a missed snapshot is lost.

### github-releases

- Measures: downloads of each release's wheel and sdist. Most installs go through
  `uv tool install git+…`, which counts as a clone, not a download — read this as a floor.
- Read with: `gh api repos/TensorAtelier/arcsong/releases --jq '.[] | {tag:.tag_name, assets:[.assets[]|{name,download_count}]}'`
- Lag: live.

## Snapshots

| Date | Stars | Unique cloners (14 d) | Views (14 d, unique) | Release downloads | Notes |
|---|---|---|---|---|---|
| 2026-10-17 | 0 | 9 | 3 | 1 | Baseline. Never announced; cloners are mostly CI (first CI runs today) and the owner. |
