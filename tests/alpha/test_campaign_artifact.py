import json
from pathlib import Path

import pytest

from tradev2.research.datasets import sha256_file


def test_committed_campaign_reconciles_and_never_claims_fresh_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    result_path = root / 'research/results/campaign.json'
    if not result_path.exists():
        pytest.skip('one-shot campaign has not completed yet')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    complete = json.loads((root / 'research/manifests/initial_campaign_completion.json').read_text(encoding='utf-8'))
    assert complete['result_sha256'] == sha256_file(result_path)
    assert result['complete'] is True
    assert result['search_budget']['configurations'] == 18
    assert result['search_budget']['total_replays'] == 144
    assert len(result['trials']) == 72
    assert len(result['families']) == 6
    assert result['promoted_candidates'] == []
    assert result['dataset']['role'] == 'REUSED_HISTORICAL_DISCOVERY'
    for family in result['families']:
        metric = family['oos']
        assert family['status'] in {'REJECTED', 'INSUFFICIENT'}
        assert metric['days'] == 120
        assert metric['total_net_pnl'] == pytest.approx(
            metric['gross_pnl'] - metric['fees'] - metric['funding'] - metric['spread'] - metric['slippage'])
        assert metric['total_net_pnl'] == pytest.approx(sum(f['validation']['total_net_pnl'] for f in family['folds']))
