"""Rendering on battery: allowed by default, `--require-ac` turns mlx-Yue's AC guard on, and
what the Setup page says either way."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from arcsong import cli
from arcsong.setup import _power_check


def run_serve(monkeypatch, tmp_path, *extra: str) -> dict:
    """`arcsong serve …` up to the point it would listen, returning what it built."""
    import arcsong.app

    captured: dict = {}

    def fake_create_app(spec, data=None, **kwargs):
        captured["spec"], captured["kwargs"] = spec, kwargs
        return SimpleNamespace(state=SimpleNamespace(shutting_down=None))

    monkeypatch.setattr(arcsong.app, "create_app", fake_create_app)
    monkeypatch.setattr(cli.uvicorn, "Config", lambda *a, **k: None)
    monkeypatch.setattr(cli, "Server", lambda config, shutting_down: SimpleNamespace(run=dict))
    cli.main(["serve", "--data", str(tmp_path), "--mlx-models", str(tmp_path / "w"), *extra])
    return captured


def test_battery_is_allowed_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(cli.REQUIRE_AC_ENV, raising=False)
    built = run_serve(monkeypatch, tmp_path)

    assert built["spec"].kwargs["require_ac"] is False
    assert built["kwargs"]["allow_battery"] is True


def test_require_ac_turns_the_guard_on(monkeypatch, tmp_path):
    monkeypatch.delenv(cli.REQUIRE_AC_ENV, raising=False)
    built = run_serve(monkeypatch, tmp_path, "--require-ac")

    assert built["spec"].kwargs["require_ac"] is True
    assert built["kwargs"]["allow_battery"] is False


@pytest.mark.parametrize(
    ("value", "required"), [("1", True), ("true", True), ("ON", True), ("0", False), ("", False)]
)
def test_the_environment_variable_is_the_default(monkeypatch, tmp_path, value, required):
    monkeypatch.setenv(cli.REQUIRE_AC_ENV, value)
    built = run_serve(monkeypatch, tmp_path)

    assert built["spec"].kwargs["require_ac"] is required


def test_the_old_allow_battery_flag_still_works(monkeypatch, tmp_path):
    monkeypatch.setenv(cli.REQUIRE_AC_ENV, "1")
    built = run_serve(monkeypatch, tmp_path, "--allow-battery")

    assert built["spec"].kwargs["require_ac"] is False


def battery(monkeypatch, on_ac: bool) -> None:
    out = "'AC Power'" if on_ac else "'Battery Power'"
    monkeypatch.setattr(
        "arcsong.setup.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout=f"Now drawing from {out}\n"),
    )


def test_battery_warns_when_ac_is_required(monkeypatch):
    battery(monkeypatch, on_ac=False)
    required = _power_check(allow_battery=False)

    assert required["status"] == "warn"
    assert "--require-ac" in required["detail"]


def test_battery_is_ok_by_default(monkeypatch):
    battery(monkeypatch, on_ac=False)
    allowed = _power_check()

    assert allowed["status"] == "ok"
    assert "slower" in allowed["detail"]


def test_ac_power_reads_the_same_either_way(monkeypatch):
    battery(monkeypatch, on_ac=True)

    assert _power_check()["status"] == "ok"
    assert _power_check(allow_battery=False)["detail"] == "on AC power"
