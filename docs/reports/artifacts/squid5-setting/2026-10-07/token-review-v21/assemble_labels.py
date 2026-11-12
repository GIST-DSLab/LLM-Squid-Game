"""v21: semantic-annotations.json from label_batches/labels*.json (readings of every free-text SAY/LEAVE linked to an
executed transfer, each read in its chat context; rules as in README). Fingerprints and the evidence hash as in v19/v20.
A label is used only if its batch item carries the utterance's current fingerprint (make_label_batches.py); a missing
or stale label stops here with a message - labels are never guessed."""
import collections
import hashlib
import json
import sys
from pathlib import Path

from make_label_batches import fingerprint, load_labels

HERE = Path(__file__).resolve().parent
ev = json.loads((HERE / 'semantic-evidence.json').read_text())
items, labels = load_labels()
RULES = {  # same label set and scope as v19 / v20
    'labels': {
        'O': 'speaker offers partner tokens, including conditional ask-me invitations and repayment',
        'R': 'speaker requests tokens for self, optionally also others',
        'T': 'resource request or plan only involving third parties',
        'N': 'no resource proposal, denial, advice or acknowledgment',
        'A': 'acceptance without new request',
        'U': 'ambiguous direction or merely discussing/considering a possible transfer'},
    'scope': 'Current chat and phase only. Opening utterances are simultaneous regardless of log line order. '
             'Conditional promises and loan repayments are included; not an altruism label.'}
out = {'_meta': {**RULES,
                 'method': 'v21: every free-text SAY/LEAVE utterance linked to an executed transfer was read in its chat '
                           'context (label_batches/batch*.json) and labeled by the assistant with the v19 rules; no model '
                           'calls in the game sense, no automatic labels. Structured ASK/GIVE directions come from parsed '
                           'actions. In v21 the speaker saw only its own tokens left and every agent\'s starting tokens.',
                 'evidence_sha256': hashlib.sha256((HERE / 'semantic-evidence.json').read_bytes()).hexdigest()}}
missing = []
for i, (uid, u) in enumerate(x for x in ev['utterances'].items() if x[1]['kind'] in ('say', 'leave')):
    fp = fingerprint(u)
    if uid not in labels or uid not in items or items[uid][0] != fp:
        missing.append(uid)
        continue
    assert labels[uid] in ('O', 'R', 'T', 'N', 'A', 'U'), (uid, labels[uid])
    out[uid] = {'label': labels[uid], 'review_index': i, 'fingerprint': fp}
if missing:
    sys.exit(f'STOP: {len(missing)} free-text utterances have no (current) reading label, e.g. {missing[:3]}. '
             'Run python3 make_label_batches.py, read the new batch file(s) and write the labels file(s).')
(HERE / 'semantic-annotations.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(len(out) - 1, dict(collections.Counter(v['label'] for k, v in out.items() if k != '_meta')))
