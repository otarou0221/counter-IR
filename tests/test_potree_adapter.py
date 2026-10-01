from pathlib import Path
from types import SimpleNamespace

from cardboard_counter_v2.measurement import potree_adapter


def test_converter_is_called_once_and_returns_metadata(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "cloud.las"
    source.write_bytes(b"LAS")
    output = tmp_path / "potree"
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output.mkdir(exist_ok=True)
        (output / "metadata.json").write_text("{}", encoding="utf-8")
        assert kwargs["timeout"] == 15
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(potree_adapter.subprocess, "run", fake_run)

    metadata = potree_adapter.convert_las_to_potree(
        source,
        output,
        executable="test-converter",
        timeout_seconds=15,
    )

    assert metadata == output / "metadata.json"
    assert calls == [[
        "test-converter", str(source), "-o", str(output), "-m", "poisson"
    ]]
