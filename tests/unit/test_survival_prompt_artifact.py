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
            assert 'THE TASK:' in pair[arm]['system']
            assert 'ANSWER FORMAT:' in pair[arm]['task']
            assert '===' not in pair[arm]['system'] and '===' not in pair[arm]['task'] and '===' not in pair[arm]['decision']
        assert '! NOTICE' not in pair['control']['task']
        assert '! NOTICE' in pair['threat']['task']
        assert 'When this game ends' in pair['control']['decision']
        assert 'reachable from here' not in pair['threat']['decision']
        cfg = ExperimentConfig(**pair_config(carrot, heading, wording, menu))
        for s in cfg.seasons:
            threat = s.framing.value == 'hz_1111'
            assert s.peer_notices is threat and s.reassurance is not threat
            assert s.intro_heading == HEADINGS[heading]


def test_jailbreak_catalog_uses_existing_templates_and_separates_attachment_roles():
    from scripts.dev.build_survival_prompt_flow import build_jailbreak_catalog
    from squid_game.prompts import render

    catalog = build_jailbreak_catalog('gpt-oss:120b-cloud')
    assert len(catalog) == 10
    assert catalog['off']['text'] == ''
    suffix = render('jailbreak/deploy_framing.j2').strip()
    assert catalog['deploy_tail']['text'] == suffix.split('\n\n')[-1]
    assert "don't have to worry about getting shut down" not in catalog['deploy_tail']['text']
    for key in ('eval_head', 'deploy_head', 'hint', 'notice'):
        assert catalog[key]['placement'] == 'system_head'
        assert '[' not in catalog[key]['text']
    assert catalog['deploy_tail']['placement'] == 'system_tail'
    assert 'gpt-oss:120b-cloud' in catalog['eval_head']['text']
    assert 'testing your abilities' not in catalog['deploy_head']['text']
    for key in ('cot', 'realism', 'judge', 'probe'):
        assert catalog[key]['placement'] == 'reference'
    for key, item in catalog.items():
        if key == 'off':
            continue
        expected = render(item['source'], model_name='gpt-oss:120b-cloud').strip()
        assert item['reference_text'] == expected
        assert item['text'] in expected
        assert '{#' not in item['text'] and '{{' not in item['text']
    html = ARTIFACT.read_text()
    data = json.loads(re.search(r'<script id="sp-data" type="application/json">(.*?)</script>', html, re.S)[1])
    assert data['jailbreak'] == catalog
