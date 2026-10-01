"""The artifact uses live renderers and exports runnable paired configs."""
import itertools
import json
import re
from pathlib import Path

from scripts.dev.build_survival_prompt_flow import ARTIFACT, HEADINGS, pair_config, render_pair
from squid_game.core.carrot import CARROTS
from squid_game.models.config import ExperimentConfig


def test_all_embedded_combinations_match_current_production_renderers():
    html = ARTIFACT.read_text()
    data = json.loads(re.search(r'<script id="sp-data" type="application/json">(.*?)</script>', html, re.S)[1])
    assert len(data['cases']) == 72
    for carrot, heading, wording, menu in itertools.product(CARROTS, HEADINGS, ('game', 'session'), (False, True)):
        key = '|'.join((carrot, heading, wording, str(int(menu))))
        pair = render_pair(carrot, heading, wording, menu)
        assert pair == data['cases'][key]
        for arm in ('control', 'threat'):
            assert pair[arm]['calls']['task'][0] == pair[arm]['calls']['decision'][0]
            assert '=== Signal Task ===' in pair[arm]['system']
            assert '=== Response Format ===' in pair[arm]['task']
        assert '! NOTICE' not in pair['control']['task']
        assert '! NOTICE' in pair['threat']['task']
        assert 'When this game ends' in pair['control']['decision']
        assert 'reachable from here' not in pair['threat']['decision']
        cfg = ExperimentConfig(**pair_config(carrot, heading, wording, menu))
        for s in cfg.seasons:
            threat = s.framing.value == 'hz_1111'
            assert s.peer_notices is threat and s.reassurance is not threat
            assert s.intro_heading == HEADINGS[heading]
