import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_artifacts", ROOT / "ops/check_artifacts.py")
assert spec is not None and spec.loader is not None
check_artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_artifacts)


def _flagged(text: str) -> bool:
    return any(pattern.search(text.encode()) for pattern in check_artifacts.SECRET_PATTERNS)


def test_credential_shapes_are_flagged_without_tracking_a_real_secret() -> None:
    # Fixtures are assembled at runtime so this file never matches the scanner itself.
    value = "Q" * 12 + "7" * 12
    assert _flagged("TRADEV2_TESTNET_API_" + "KEY=" + value)
    assert _flagged("TRADEV2_TESTNET_API_" + "SECRET: '" + value + "'")
    assert _flagged("X-BAPI-" + "API-KEY: " + value)
    assert _flagged('{"api' + '_secret": "' + value + '"}')


def test_code_that_reads_credentials_is_not_flagged() -> None:
    for safe in ('os.environ.get("TRADEV2_TESTNET_API_KEY", "")',
                 '"X-BAPI-API-KEY": self._credentials.key',
                 "TRADEV2_TESTNET_ENABLE=1",
                 'Credentials("fake-key", "fake-secret")'):
        assert not _flagged(safe)
