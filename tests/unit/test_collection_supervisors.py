from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("script", ["ops/continue_public_bars.ps1", "ops/continue_public_oi.ps1"])
def test_supervisors_keep_evidence_status_and_logs_under_the_data_root(script: str) -> None:
    text = (ROOT / script).read_text(encoding="utf-8")
    # Code may run from a pinned checkout; evidence, status and logs belong to the data root.
    assert "$campaign = Join-Path $dataRoot ('runtime\recorder\\" in text
    assert "Join-Path $root ('runtime" not in text
    assert "--root $dataRoot" in text
    assert "GetPathRoot($dataRoot)" in text
    assert "$env:PYTHONPATH = Join-Path $root 'src'" in text
