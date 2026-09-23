from pathlib import Path

import pytest

from tradev2.research import microstructure


@pytest.mark.parametrize("clean,uninterrupted", [(False, True), (True, False)])
def test_analysis_rejects_dirty_or_interrupted_recordings(
    monkeypatch: pytest.MonkeyPatch, clean: bool, uninterrupted: bool,
) -> None:
    monkeypatch.setattr(microstructure, "inspect_recording",
                        lambda _path, _run_id: {"provenance_clean": clean,
                                                 "uninterrupted_feed": uninterrupted})
    with pytest.raises(ValueError, match="clean provenance and uninterrupted feed"):
        microstructure.analyze(Path("unused.sqlite"), "recorder-test")
