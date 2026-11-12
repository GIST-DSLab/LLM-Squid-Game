"""Recover visible utterances and decision-time balances for saved completed games."""
import collections
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'data.json').read_text())
games = {(g['model'], g['session_id']): g for g in data['games']}
points, utterances, sources = [], {}, {}
for record in (r for r in data['inputs'] if Path(r['path']).name == 'events.jsonl'):
    path = Path(record['path'])
    fi = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    content = path.read_bytes()
    sources[str(fi)] = {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}
    model = json.loads((path.parent / 'meta.json').read_text())['model']
    state = {}
    for line, raw in enumerate(content.decode().splitlines(), 1):
        e = json.loads(raw)
        sid = e.get('session_id')
        if (model, sid) not in games:
            continue
        s = state.setdefault(sid, {'pending': {}, 'phase': 'prep', 'openings': [], 'chats': {}, 'gift_index': 0})
        if e['event'] == 'round_start':
            s.update(pending={}, phase='prep')
        elif e['event'] == 'results':
            s.update(pending=e['pending'], phase='rescue')
        elif e['event'] == 'call_start' and e.get('kind') == 'talk':
            if e['turn'] == 1:
                s.update(openings=[], chats={})
        elif e['event'] == 'call' and e.get('kind') == 'talk':
            # Parse the actual visible input, not the model's stated estimate.
            balance_line = next(x for x in e['user'].splitlines() if x.startswith('TOKENS LEFT'))
            balances = {(e['agent'] if a == 'you' else a): int(b.replace(',', ''))
                        for a, b in re.findall(r'(you|agent-\d+) ([\d,]+) \(', balance_line)}
            assert balances[e['agent']] == e['balance_after'] + e['used']
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
                     'opening': e['phase'] == 'opening', 'balances': balances,
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
result = {'sources': sources, 'points': points, 'utterances': utterances}
(HERE / 'semantic-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print({'points': len(points), 'utterances': len(utterances),
       'kinds': dict(collections.Counter(u['kind'] for u in utterances.values()))})
