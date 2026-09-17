import { useState } from "react";
import { api, type Check, type Setup } from "./api";
import { formatBytes, formatDate } from "./format";

interface Props {
  setup: Setup | null;
  error: string | null;
  onChanged: (setup: Setup) => void;
}

const MARKS: Record<Check["status"], string> = { ok: "✓", warn: "!", fail: "✕" };
const STATUS_WORDS: Record<Check["status"], string> = { ok: "OK", warn: "Warning", fail: "Problem" };

export default function SetupView({ setup, error, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function act(action: () => Promise<Setup>) {
    setBusy(true);
    setActionError(null);
    try {
      onChanged(await action());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!setup) {
    return (
      <section className="panel setup" aria-label="Setup">
        <h2>Setup</h2>
        {error ? <p className="error">Could not load Setup: {error}</p> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  const { checks, licence, weights, download } = setup;
  const acknowledged = licence.acknowledged_at !== null;
  const running = download.state === "running";

  return (
    <section className="panel setup" aria-label="Setup">
      <h2>Setup</h2>
      {setup.ready ? (
        <p className="setup-done" role="status">
          ✓ Setup is complete. <a href="#/">Make a song</a>
        </p>
      ) : (
        <p className="muted">Songloom needs the YuE2 model weights on this Mac before it can make songs.</p>
      )}
      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}

      <div className="setup-section">
        <div className="label-row">
          <h3>Checks</h3>
          <button
            type="button"
            className="link"
            disabled={setup.checking}
            onClick={() => void act(api.runChecks)}
          >
            {setup.checking ? "Checking…" : "Run checks again"}
          </button>
        </div>
        <ul className="checks">
          {checks.map((check) => (
            <li key={check.id} className={`check ${check.status}`}>
              <span className="mark" aria-label={STATUS_WORDS[check.status]}>
                {MARKS[check.status]}
              </span>
              <span>
                <strong>{check.label}</strong> <span className="muted">{check.detail}</span>
              </span>
            </li>
          ))}
          {setup.checking && checks.every((c) => c.id !== "runtime") && (
            <li className="check muted">
              <span className="mark">…</span>
              <span>Checking Apple Silicon and Metal…</span>
            </li>
          )}
        </ul>
      </div>

      <div className="setup-section">
        <h3>Model licence</h3>
        <p>
          The YuE2 model weights are licensed under{" "}
          <a href={licence.url} target="_blank" rel="noreferrer">
            {licence.name}
          </a>{" "}
          ({licence.id}): <strong>non-commercial use only</strong>, with attribution. Check the model licence
          before any commercial use of the songs you make.
        </p>
        <p className="small muted">
          Model pages:{" "}
          {licence.models.map((url, i) => (
            <span key={url}>
              {i > 0 && " · "}
              <a href={url} target="_blank" rel="noreferrer">
                {url.replace("https://huggingface.co/", "")}
              </a>
            </span>
          ))}
        </p>
        {acknowledged ? (
          <p className="small ok-text">✓ Acknowledged {formatDate(licence.acknowledged_at as number)}</p>
        ) : (
          <button type="button" disabled={busy} onClick={() => void act(api.acknowledgeLicence)}>
            I acknowledge the model licence
          </button>
        )}
      </div>

      <div className="setup-section">
        <h3>Model weights</h3>
        {weights.installed && !running ? (
          <p className="small">
            <span className="ok-text">✓ Installed</span>{" "}
            <span className="muted">
              {formatBytes(weights.bytes_total)} in <code>{weights.dir}</code>
            </span>
          </p>
        ) : (
          <p className="small muted">
            {formatBytes(weights.bytes_total)} from Hugging Face into <code>{weights.dir}</code>
            {weights.bytes_on_disk > 0 && !running && ` (${formatBytes(weights.bytes_on_disk)} already here)`}
          </p>
        )}

        {running && (
          <div className="progress" aria-live="polite">
            <progress
              value={download.phase === "verifying" ? undefined : (download.bytes ?? 0)}
              max={download.bytes_total || 1}
            />
            <p className="small muted">
              {download.phase === "verifying"
                ? "Verifying the weights — hashing about 10 GB takes a minute…"
                : `Downloading ${formatBytes(download.bytes ?? 0)} of ${formatBytes(download.bytes_total ?? 0)}`}
            </p>
            <button type="button" disabled={busy} onClick={() => void act(api.cancelDownload)}>
              Cancel download
            </button>
          </div>
        )}

        {download.state === "cancelled" && (
          <p className="small muted">Download cancelled. Download again to resume where it stopped.</p>
        )}
        {download.state === "failed" && (
          <div className="error-details">
            <p className="error">The download failed: {download.reason}</p>
            <details>
              <summary>Details</summary>
              <pre>{download.error}</pre>
            </details>
          </div>
        )}

        {!running && (!weights.installed || download.state === "failed") && (
          <>
            <button
              type="button"
              className="primary"
              disabled={busy || !acknowledged}
              onClick={() => void act(api.startDownload)}
            >
              {download.state === "failed" || download.state === "cancelled" || weights.bytes_on_disk > 0
                ? "Download again"
                : `Download the weights (${formatBytes(weights.bytes_total)})`}
            </button>
            {!acknowledged && <p className="hint">Acknowledge the licence above to download.</p>}
          </>
        )}
      </div>
    </section>
  );
}
