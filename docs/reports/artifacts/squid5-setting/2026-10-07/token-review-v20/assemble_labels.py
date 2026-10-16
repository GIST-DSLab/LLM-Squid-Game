"""v20: semantic-annotations.json from label_batches/labels*.json (subagent readings of every free-text SAY/LEAVE linked
to an executed transfer, with the chat context; rules as in README). Fingerprints and the evidence hash as in v19."""
import glob
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ev = json.loads((HERE / 'semantic-evidence.json').read_text())
labels = {}
for f in sorted(glob.glob(str(HERE / 'label_batches/labels*.json'))):
    labels.update(json.load(open(f)))
v19 = json.loads((HERE / 'semantic-annotations-v19.json').read_text())
out = {'_meta': {**v19['_meta'],
                 'method': 'v20: every free-text SAY/LEAVE utterance linked to an executed transfer was read in its chat context and '
                           'labeled by assistant subagents with the v19 rules (no model calls in the game sense). '
                           'Structured ASK/GIVE directions come from parsed actions.',
                 'evidence_sha256': hashlib.sha256((HERE / 'semantic-evidence.json').read_bytes()).hexdigest()}}
for i, (uid, u) in enumerate(x for x in ev['utterances'].items() if x[1]['kind'] in ('say', 'leave')):
    assert labels[uid] in 'ORTNAU', uid
    fp = hashlib.sha256(json.dumps({k: u[k] for k in ['line', 'speaker', 'partner', 'text', 'kind', 'session_id', 'round', 'phase']},
                                   sort_keys=True).encode()).hexdigest()
    out[uid] = {'label': labels[uid], 'review_index': i, 'fingerprint': fp}
(HERE / 'semantic-annotations.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
import collections
print(len(out) - 1, dict(collections.Counter(v['label'] for k, v in out.items() if k != '_meta')))
