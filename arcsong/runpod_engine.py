"""The RunPod Engine: each job runs on the user's own RunPod account (`arcsong.runpod_app`).

The Modal Engine's local half, with RunPod's call underneath: one `render` job per request,
whose stream carries the stage events and then the Take's files in chunks.
"""

from __future__ import annotations

import base64
import queue
import threading
from typing import Any

from arcsong.engine import CancelCheck, Cancelled, Emit
from arcsong.modal_engine import POLL_SECONDS, ModalEngine

APP_NAME = "arcsong"
# A cold worker pulls the runtime image before it starts (~4 minutes in X-002), then the song.
STREAM_SECONDS = 45 * 60
_DONE = object()


class RunPodEngine(ModalEngine):
    mac_draft_advice = (
        "This Draft was made by the Mac engine, which RunPod can't continue. Finalize it with "
        "--engine mlx, or render the song again on RunPod."
    )
    cancelled_elsewhere = "The job was stopped on RunPod (from its console or the API)."

    def load(self) -> None:
        """Nothing to load here: the model lives on RunPod's workers. A missing app or key only
        shows at the first job, in RunPod's own words."""
        if self._remote is None:
            import runpod

            self._queue = runpod.Queue(app=self.app_name, name="render")
            self._remote = self._call

    def _call(self, job: dict[str, Any], cancelled: CancelCheck, emit: Emit) -> dict[str, Any]:
        if "files" in job:  # job input is JSON
            files = {name: base64.b64encode(data).decode() for name, data in job["files"].items()}
            job = {**job, "files": files}
        handle = self._queue.spawn(job=job)
        chunks: queue.Queue = queue.Queue()
        threading.Thread(target=_read, args=(handle, chunks), daemon=True).start()
        header: dict[str, Any] | None = None
        parts: dict[str, list[bytes]] = {}
        while True:
            if cancelled():
                handle.cancel()
                raise Cancelled(job["kind"])
            try:
                chunk = chunks.get(timeout=POLL_SECONDS)
            except queue.Empty:
                continue
            if chunk is _DONE:
                break
            if isinstance(chunk, BaseException):
                raise chunk
            kind = chunk.get("type")
            if kind == "result":
                header = chunk
            elif kind == "file":
                parts.setdefault(chunk["name"], []).append(base64.b64decode(chunk["data"]))
            else:
                emit(chunk)
        if header is None:
            raise self._failure(handle)
        files = {name: b"".join(data) for name, data in parts.items()}
        if {name: len(data) for name, data in files.items()} != header.get("sizes", {}):
            raise RuntimeError("RunPod returned the song incomplete; render it again.")
        if "abc" in header:
            return {"abc": header["abc"]}
        return {"files": files, "audio_seconds": header["audio_seconds"]}

    def _failure(self, handle) -> Exception:
        """A stream that ended with no result: the job was cancelled there, or failed."""
        status = handle.status()
        if status == "CANCELLED":
            return RuntimeError(self.cancelled_elsewhere)
        try:
            handle.result(timeout=30)  # a failed job raises its worker's error here
        except Exception as error:  # noqa: BLE001 — the remote traceback; its last line says why
            lines = [line for line in str(error).splitlines() if line.strip()]
            return RuntimeError(f"RunPod: {lines[-1].strip() if lines else error}")
        return RuntimeError(f"RunPod ended the job with no song (status {status}).")


def _read(handle, chunks: queue.Queue) -> None:
    try:
        for chunk in handle.stream(timeout=STREAM_SECONDS):
            chunks.put(chunk)
    except Exception as error:  # noqa: BLE001 — handed to the waiting loop
        chunks.put(error)
    finally:
        chunks.put(_DONE)
