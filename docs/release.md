# Cutting a release

Arcsong is installed straight from git, so a release is a tag, a set of notes and two built
artifacts. There is no PyPI package (see `PLAN.md`, M6) — the version number in
`pyproject.toml` and the tag are the only places a version lives.

## Before tagging

```sh
uv run pytest -q                       # everything on the fake Engine
uv run ruff check .
cd web && npm run typecheck && npm run build   # the build is committed; commit it if it changed
```

On real weights, on AC power, with other model servers closed:

```sh
ARCSONG_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py
```

Then check the package is what a user gets:

```sh
rm -rf dist && uv build
uv tool install --force "git+https://github.com/TensorAtelier/arcsong@main"
which -a arcsong spike        # arcsong only; spike must not be installed
arcsong serve                 # Setup page comes up, then stop it
uv tool uninstall arcsong
```

## Tagging

1. Bump `version` in `pyproject.toml` and add the section to `CHANGELOG.md`.
2. Commit, push, and confirm the tree is clean.
3. Tag and push the tag:

```sh
git tag -a v0.1.0 -m "arcsong v0.1.0"
git push origin v0.1.0
```

4. Create the release with the built artifacts:

```sh
gh release create v0.1.0 dist/* --title "arcsong v0.1.0" --notes-file <notes>
```

## Notes worth keeping in the release text

- What the release needs: macOS on Apple Silicon, ~24 GB memory comfortably, ~11 GB disk for
  the weights, AC power to render.
- That the model weights are CC BY-NC 4.0 and downloaded on first run, not bundled.
- The install and upgrade commands, since they are the whole distribution story.

## Undoing one

A tag and a release can both be removed (`gh release delete v0.1.0 --cleanup-tag`), which is
why nothing here is irreversible. Anything published to a package index would not be — that is
the reason M6 deliberately stops short of one.
