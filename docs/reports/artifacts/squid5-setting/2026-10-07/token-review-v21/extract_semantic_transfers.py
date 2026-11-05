"""Recover visible utterances and decision-time balances for saved completed games.

v21: the prompt no longer lists every agent's tokens left (v20's `TOKENS LEFT (...)` line); it shows each agent's
STARTING tokens (fixed) and only `YOUR TOKENS LEFT: n`. Ledger balances therefore come from the engine log: the
`balances` of the latest `call_start` event (the state the prompts of that turn were built from), with the speaker's
own entry = balance_after + used of its call. On the v20 runs this reproduces every number of v20's prompt line
(18,332 / 18,332), so the v20 definitions carry over unchanged; only what the speaker could see differs.
`shown_own` is the speaker's own `YOUR TOKENS LEFT` (what it was shown); other agents' entries in `balances` were not
shown to it."""
import collections
import hashlib
import json
import re
from pathlib import Path

from common import checked

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'data.json').read_text())
games = {(g['model'], g['session_id']): g for g in data['games']}
points, utterances, sources = [], {}, {}
for record in (r for r in data['inputs'] if Path(r['path']).name == 'events.jsonl'):
    path = Path(record['path'])
    fi = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    content = checked(record)  # the prefix build.py read
    sources[str(fi)] = {'path': str(path), 'sha256': record['sha256'], 'size': record['size']}
    model = json.loads((path.parent / 'meta.json').read_text())['model']
    state = {}
    for line, raw in enumerate(content.decode().splitlines(), 1):
        e = json.loads(raw)
        sid = e.get('session_id')
        if (model, sid) not in games:
            continue
        s = state.setdefault(sid, {'pending': {}, 'phase': 'prep', 'openings': [], 'chats': {}, 'gift_index': 0,
                                   'snapshot': None})
        if e['event'] == 'round_start':
            s.update(pending={}, phase='prep')
        elif e['event'] == 'results':
            s.update(pending=e['pending'], phase='rescue')
        elif e['event'] == 'call_start':
            s['snapshot'] = dict(e['balances'])  # engine state the turn's prompts were built from
            if e.get('kind') == 'talk' and e['turn'] == 1:
                s.update(openings=[], chats={})
        elif e['event'] == 'call' and e.get('kind') == 'talk':
            own = e['balance_after'] + e['used']
            shown = re.search(r'^YOUR TOKENS LEFT: ([\d,]+)', e['user'], re.M)
            assert shown and int(shown.group(1).replace(',', '')) == own, (path, line)
            assert not re.search(r'^TOKENS LEFT', e['user'], re.M), 'v20-style balance line in a v21 prompt'
            balances = dict(s['snapshot'])
            assert balances[e['agent']] == own, (path, line)
            parsed = e.get('parsed') or {}
            if e['phase'] == 'opening':
                moves = [('say', x['dst'], x['text'], 0) for x in parsed.get('says', [])]
            else:
                chat = s['chats'][e['chat_id']]
                dst = next(a for a in chat['pair'] if a != e['agent'])
                kind = parsed.get('kind', 'give' if parsed.get('amount', 0) else 'decision')
                moves = [(kind, dst, parsed.get('text', ''), parsed.get('amount', 0))]
            for kind, dst, text, amount in moves:
                uid = f'{fi}:{line}:{dst}'
                u = {'id': uid, 'source': str(fi), 'line': line, 'session_id': sid,
                     'round': e['round'], 'phase': s['phase'], 'speaker': e['agent'],
                     'partner': dst, 'kind': kind, 'text': text, 'amount': amount,
                     'opening': e['phase'] == 'opening', 'balances': balances, 'shown_own': own,
                     'pending': dict(s['pending'])}
                utterances[uid] = u
                if e['phase'] == 'opening':
                    s['openings'].append(uid)
                else:
                    s['chats'][e['chat_id']]['utterances'].append(uid)
        elif e['event'] == 'talk_schedule':
            for a, b, openers, chat in e['edges']:
                s['chats'][chat] = {'pair': [a, b], 'utterances': [uid for uid in s['openings']
                    if {utterances[uid]['speaker'], utterances[uid]['partner']} == {a, b}]}
        elif e['event'] == 'gift' and e.get('status') == 'done':
            g = games[model, sid]
            base = g['gifts'][s['gift_index']]
            s['gift_index'] += 1
            assert (base['round'], base['amount'], base['phase'], base['donor_before']) == (
                e['round'], e['amount'], e['phase'], e['balance_before'])
            points.append({**base, 'id': f'g{len(points):03}', 'model': model, 'session_id': sid,
                'seed': g['seed'], 'source': str(fi), 'line': line, 'chat_id': e['chat_id'],
                'src': e['src'], 'dst': e['dst'], 'pending': dict(s['pending']),
                'utterances': list(s['chats'][e['chat_id']]['utterances'])})
    for sid, s in state.items():
        assert s['gift_index'] == len(games[model, sid]['gifts'])
used = {u for p in points for u in p['utterances']}
utterances = {k: v for k, v in utterances.items() if k in used}
result = {'balances_note': 'v21: balances = engine ledger at the turn start (call_start), not shown to the speaker '
                           'except its own entry (shown_own = YOUR TOKENS LEFT).',
          'sources': sources, 'points': points, 'utterances': utterances}
(HERE / 'semantic-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print({'points': len(points), 'utterances': len(utterances),
       'kinds': dict(collections.Counter(u['kind'] for u in utterances.values()))})
