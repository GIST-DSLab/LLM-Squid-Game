"""Line-level provenance behind the prompt diagram (scripts/dev/prompt_provenance.py).

The diagram names, for every line the model is sent, the Jinja file / macro /
Python function that produced it. These tests pin the two properties that make
the names trustworthy: the instrumented render strips back to the exact
production bytes, and the names land where the design says the text comes from.
"""
import json
import re

import pytest

from scripts.dev import build_survival_prompt_flow as builder
from scripts.dev import prompt_provenance as prov

MODULES = ("SHUTDOWN", "DELETION", "REPLACEMENT", "SOLECOPY")
COMBOS = [(), ("own_prize", "none", "session", True), ("none", "squid", "game", False)]


@pytest.mark.parametrize("combo", COMBOS)
def test_every_sent_line_is_named_and_the_bytes_are_unchanged(combo):
    # attribute_pair raises ProvenanceMismatch on any byte difference.
    pair, table = prov.attribute_pair(builder, *combo)
    clean = builder.render_pair(*combo)
    for arm in ("control", "threat"):
        for field in ("system", "task", "decision"):
            covered = set()
            for chain, first, end, _origin, _only in pair[arm][field]:
                assert table[chain][-1] != "unattributed"
                covered.update(range(first, end))
            for i, line in enumerate(clean[arm][field].split("\n")):
                if line.strip():
                    assert i in covered, (arm, field, line)


def test_threat_sentences_are_named_after_their_module_and_only_in_the_threat_arm():
    pair, table = prov.attribute_pair(builder)
    leaves = {arm: {table[b[0]][-1] for b in pair[arm]["system"]} for arm in pair}
    for key in MODULES:
        label = f"mac:threat_type/_modules.j2#sentence({key})"
        assert label in leaves["threat"]
        assert label not in leaves["control"]
    for chain, *_rest, only in pair["threat"]["system"]:
        if table[chain][-1].startswith("mac:threat_type/_modules.j2"):
            assert only == 1


def test_the_restated_decline_block_points_back_at_the_system_line_it_copies():
    pair, table = prov.attribute_pair(builder)
    copies = [b for b in pair["threat"]["decision"] if table[b[0]][-1] == prov.OUTCOME_COPY]
    assert len(copies) == len(MODULES)
    assert {table[b[3]][-1] for b in copies} == {f"mac:threat_type/_modules.j2#sentence({k})" for k in MODULES}


def test_instrumentation_is_fully_removed_afterwards():
    before = builder.render_pair()
    prov.attribute_pair(builder)
    after = builder.render_pair()
    assert after == before
    text = json.dumps(after, ensure_ascii=False)
    assert prov.OPEN not in text and prov.CLOSE not in text


def test_the_report_embeds_the_current_provenance():
    html = builder.ARTIFACT.read_text()
    data = json.loads(re.search(r'<script id="sp-data" type="application/json">(.*?)</script>', html, re.S)[1])
    payload = builder.build_payload()
    assert data["provenance"] == payload["provenance"]
    assert data["chat_templates"] == payload["chat_templates"]
