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
