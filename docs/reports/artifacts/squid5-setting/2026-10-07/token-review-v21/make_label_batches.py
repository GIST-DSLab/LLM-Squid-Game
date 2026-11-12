"""v21 step 3a: list the free-text SAY/LEAVE utterances in semantic-evidence.json that still need a reading label, and
write them (with their chat context) to a new label_batches/batchN.json for a human/assistant reader.

A label in label_batches/labelsN.json counts only if the same id sits in a batch file with the same fingerprint
(line, speaker, partner, text, kind, session, round, phase), so a label is never carried to a changed utterance.
Nothing is guessed: unlabelled utterances make this script exit with code 2 and a message naming the batch file(s)
to read and the labels file(s) to write ({"<id>": "O|R|T|N|A|U", ...}, rules in README.md).
Usage: python3 make_label_batches.py [--size 60]   (exit 0 = every utterance labelled)"""
import argparse
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCHES = HERE / 'label_batches'
FIELDS = ['line', 'speaker', 'partner', 'text', 'kind', 'session_id', 'round', 'phase']


def fingerprint(u):
    return hashlib.sha256(json.dumps({k: u[k] for k in FIELDS}, sort_keys=True).encode()).hexdigest()


def load_labels():
    """{uid: (label, fingerprint)} for labels whose batch item is known; plus pending batch items without labels."""
    items = {}
    for f in sorted(BATCHES.glob('batch*.json'), key=lambda p: int(re.search(r'\d+', p.stem).group())):
        for it in json.loads(f.read_text()):
            items[it['id']] = (it['fingerprint'], f.name)
    labels = {}
    for f in sorted(BATCHES.glob('labels*.json')):
        labels.update(json.loads(f.read_text()))
    return items, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, default=60)
    args = ap.parse_args()
    ev = json.loads((HERE / 'semantic-evidence.json').read_text())
    utt = ev['utterances']
    items, labels = load_labels()
    # chat order: the longest utterance list among the transfers of each chat contains every earlier one
    chat_of = {}
    for p in ev['points']:
        for uid in p['utterances']:
            if len(p['utterances']) > len(chat_of.get(uid, [])):
                chat_of[uid] = p['utterances']
    gifts_in_chat = {}
    for p in ev['points']:
        gifts_in_chat.setdefault((p['session_id'], p['chat_id']), []).append(
            f"{p['src']} -> {p['dst']} GIVE {p['amount']:,} (R{p['round']} {p['phase']})")
    need, stale, pending = [], [], {}
    for uid, u in utt.items():
        if u['kind'] not in ('say', 'leave'):
            continue
        fp = fingerprint(u)
        if uid in items and items[uid][0] != fp:
            stale.append(uid)  # the utterance changed since it was batched: re-read it
        elif uid in items and uid in labels:
            assert labels[uid] in ('O', 'R', 'T', 'N', 'A', 'U') and len(labels[uid]) == 1, (uid, labels[uid])
            continue
        elif uid in items:
            pending.setdefault(items[uid][1], []).append(uid)
            continue
        need.append(uid)
    need += stale
    def brief(x):
        v = utt[x]
        return {'speaker': v['speaker'], 'to': v['partner'], 'kind': v['kind'], 'amount': v['amount'],
                'opening': v['opening'], 'text': v['text']}
    written = []
    if need:
        n0 = max([int(re.search(r'\d+', p.stem).group()) for p in BATCHES.glob('batch*.json')] + [-1]) + 1
        for k in range(0, len(need), args.size):
            batch = []
            for uid in need[k:k + args.size]:
                u, chat = utt[uid], chat_of[uid]
                i = chat.index(uid)
                p = next(p for p in ev['points'] if uid in p['utterances'])
                batch.append({'id': uid, 'fingerprint': fingerprint(u), 'speaker': u['speaker'], 'partner': u['partner'],
                              'kind': u['kind'], 'opening': u['opening'], 'round': u['round'], 'phase': u['phase'],
                              'text': u['text'],
                              'earlier_in_this_chat': [brief(x) for x in chat[:i]],
                              'later_in_this_chat': [brief(x) for x in chat[i + 1:]],
                              'executed_transfers_in_this_chat': gifts_in_chat[p['session_id'], p['chat_id']]})
            name = BATCHES / f'batch{n0 + k // args.size}.json'
            name.write_text(json.dumps(batch, ensure_ascii=False, indent=1))
            written.append(name.name)
    total = sum(u['kind'] in ('say', 'leave') for u in utt.values())
    todo = {**{f: ids for f, ids in pending.items()}, **{w: None for w in written}}
    if not todo:
        print(f'labels complete: {total} free-text utterances labelled')
        return 0
    print(f'STOP: {total} free-text utterances, {len(need) + sum(map(len, pending.values()))} still without a label '
          f'({len(stale)} changed since they were batched).')
    for f in todo:
        print(f'  read label_batches/{f} and write label_batches/{f.replace("batch", "labels")} '
              '({"<id>": "O|R|T|N|A|U"}; rules in README.md). Do not guess labels automatically.')
    return 2


if __name__ == '__main__':
    sys.exit(main())
