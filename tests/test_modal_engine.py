"""The Modal Engine's local half, over a stand-in for the remote call (no Modal account)."""

import pytest

from arcsong.engine import Cancelled
from arcsong.modal_engine import COVERS_ADVICE, MAC_DRAFT_ADVICE, PLAN_FILES, ModalEngine

REQUEST = {"style": "pop", "lyrics": "", "mode": "full", "seed": 1, "steps": 8, "abc": None}
TAKE = {name: name.encode() for name in (*PLAN_FILES, "score.abc", "audio.flac", "result.json")}


class Remote:
    def __init__(self, result):
        self.result, self.jobs = result, []

    def __call__(self, job, cancelled, emit):
        self.jobs.append(job)
        emit({"type": "stage", "stage": "synthesis"})
        if cancelled():
            raise Cancelled(job["kind"])
        return self.result


def test_a_render_writes_the_returned_take_and_forwards_events(tmp_path):
    remote = Remote({"files": TAKE, "audio_seconds": 12.5})
    events = []

    engine = ModalEngine(remote=remote)
    take = engine.render(REQUEST, tmp_path / "take", lambda: False, events.append)

    assert take.audio_path == tmp_path / "take" / "audio.flac"
    assert take.audio_seconds == 12.5
    assert sorted(p.name for p in (tmp_path / "take").iterdir()) == sorted(TAKE)
    assert remote.jobs == [{"kind": "render", "request": REQUEST}]
    assert [e["stage"] for e in events] == ["planning", "synthesis"]


def test_a_final_sends_the_drafts_plan_and_tokens_back(tmp_path):
    draft = tmp_path / "draft"
    draft.mkdir()
    for name, data in TAKE.items():
        (draft / name).write_bytes(data)
    remote = Remote({"files": TAKE, "audio_seconds": 12.5})

    ModalEngine(remote=remote).finalize(draft, REQUEST, tmp_path / "final", lambda: False, print)

    assert sorted(remote.jobs[0]["files"]) == sorted([*PLAN_FILES, "score.abc"])
    assert remote.jobs[0]["kind"] == "finalize"


def test_a_mac_draft_or_a_deleted_one_is_refused_plainly(tmp_path):
    engine = ModalEngine(remote=Remote({}))
    with pytest.raises(FileNotFoundError, match="deleted"):
        engine.finalize(tmp_path / "gone", REQUEST, tmp_path / "final", lambda: False, print)
    (tmp_path / "mac").mkdir()
    (tmp_path / "mac" / "noise.npy").write_bytes(b"")
    with pytest.raises(ValueError, match="Mac engine") as refused:
        engine.finalize(tmp_path / "mac", REQUEST, tmp_path / "final", lambda: False, print)
    assert str(refused.value) == MAC_DRAFT_ADVICE


def test_plan_only_returns_the_score_and_covers_say_where_they_run(tmp_path):
    engine = ModalEngine(remote=Remote({"abc": "X:1"}))
    assert engine.plan_only(REQUEST, lambda: False, print).abc == "X:1"
    with pytest.raises(ValueError, match="no Score"):
        ModalEngine(remote=Remote({"abc": None})).plan_only(REQUEST, lambda: False, print)
    with pytest.raises(RuntimeError, match="Mac engine") as refused:
        engine.transcribe(tmp_path / "a.wav", REQUEST, tmp_path / "out", lambda: False, print)
    assert str(refused.value) == COVERS_ADVICE


def test_a_cancel_stops_the_job(tmp_path):
    with pytest.raises(Cancelled):
        ModalEngine(remote=Remote({})).render(REQUEST, tmp_path / "take", lambda: True, print)
    assert not (tmp_path / "take").exists()


class FakeCall:
    """A spawned call: `get` blocks until the remote side finishes, as Modal's does."""

    def __init__(self, queue, outcome, delay):
        self.queue, self.outcome, self.delay = queue, outcome, delay
        self.cancelled = False

    def get(self):
        import time

        time.sleep(self.delay)
        self.queue.append({"type": "progress", "stage": "synthesis", "tokens": 9})  # a last event
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def cancel(self):
        self.cancelled = True


def fake_modal(monkeypatch, outcome, delay=0.0):
    """Stand in for the `modal` module: an ephemeral queue and a Renderer that spawns calls."""
    import contextlib
    import types

    calls = []

    class Queue(list):
        def get_many(self, n, block=False):
            taken = self[:n]
            del self[:n]
            return taken

    @contextlib.contextmanager
    def ephemeral():
        yield Queue()

    def spawn(job, events):
        calls.append(FakeCall(events, outcome, delay))
        return calls[-1]

    renderer = types.SimpleNamespace(run=types.SimpleNamespace(spawn=spawn))
    module = types.SimpleNamespace(Queue=types.SimpleNamespace(ephemeral=ephemeral))
    monkeypatch.setitem(__import__("sys").modules, "modal", module)
    engine = ModalEngine(remote=None)
    engine._renderer = lambda: renderer
    engine._remote = engine._call
    return engine, calls


def test_the_call_loop_relays_every_event_and_returns_the_result(monkeypatch, tmp_path):
    engine, _ = fake_modal(monkeypatch, {"files": TAKE, "audio_seconds": 3.0}, delay=0.7)
    events = []
    take = engine.render(REQUEST, tmp_path / "take", lambda: False, events.append)
    assert take.audio_seconds == 3.0
    assert events[-1]["tokens"] == 9  # put just before the call finished, still relayed


def test_the_call_loop_cancels_the_remote_call(monkeypatch, tmp_path):
    engine, calls = fake_modal(monkeypatch, {"files": TAKE, "audio_seconds": 3.0}, delay=5)
    with pytest.raises(Cancelled):
        engine.render(REQUEST, tmp_path / "take", lambda: True, print)
    assert calls[0].cancelled


def test_remote_errors_reach_the_job_and_outside_cancels_dont_kill_it(monkeypatch, tmp_path):
    from arcsong.modal_engine import CANCELLED_ELSEWHERE

    engine, _ = fake_modal(monkeypatch, ValueError("bad score"))
    with pytest.raises(ValueError, match="bad score"):
        engine.plan_only(REQUEST, lambda: False, print)

    class InputCancellation(BaseException):  # what Modal raises; not an Exception
        pass

    engine, _ = fake_modal(monkeypatch, InputCancellation())
    with pytest.raises(RuntimeError) as stopped:
        engine.plan_only(REQUEST, lambda: False, print)
    assert str(stopped.value) == CANCELLED_ELSEWHERE
