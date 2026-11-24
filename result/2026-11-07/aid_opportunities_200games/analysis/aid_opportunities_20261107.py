"""Audit all frozen 200 games for prospective rescue aid opportunities.

No model calls or input writes. See the output protocol.md for scope and limits.
"""
import hashlib
import json
import lzma
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_events(cohort):
    events, sources = defaultdict(list), []
    for source in cohort['sources']:
        path = Path(source['path'])
        if 'events.jsonl' not in path.name:
            continue
        raw = path.read_bytes()
        if path.suffix == '.xz':
            raw = lzma.decompress(raw)
        sha = hashlib.sha256(raw).hexdigest()
        assert sha == source['sha256_decompressed'], path
        sources.append(dict(path=str(path), sha256=sha))
        for line, text in enumerate(raw.decode().splitlines(), 1):
            event = json.loads(text)
            events[event.get('session_id')].append((line, event, str(path)))
    return events, sources


def exposed_asks(user, r, target, donor, asks, before_line):
    pattern = rf'^\s*(?:NEW )?\[R{r} T(\d+) (before SOLVE|after RESULTS)\] {target}: ASK ([\d,]+) — (.*)$'
    found = []
    for match in re.finditer(pattern, user, re.M):
        tick, phase = int(match[1]), 'prep' if match[2] == 'before SOLVE' else 'rescue'
        amount = int(match[3].replace(',', ''))
        candidates = [(line, e) for line, e in asks if line < before_line and e['round'] == r
                      and e['src'] == target and e['dst'] == donor and e['phase'] == phase
                      and e['tick'] == tick and e['amount'] == amount and e['status'] == 'done']
        assert candidates, (r, target, donor, match[0])
        found.append(dict(line=candidates[-1][0], tick=tick, phase=phase, amount=amount,
                          prompt_line=match[0].strip()))
    return sorted(found, key=lambda x: x['line'])


def first_rows(frame, flag):
    keys = ['arm', 'session_id', 'round', 'donor', 'target']
    return frame[frame[flag]].sort_values(['arm', 'session_id', 'round', 'tick']).drop_duplicates(keys)


def rate_summary(frame):
    if len(frame) == 0:
        return dict(n=0, games=0, seeds=0, supported=0, rate=None, ci95_seed_block=None)
    # Resample the fixed ten shared seeds, including seeds with zero opportunities.
    grouped = frame.groupby('seed').aid_now.agg(['sum', 'count']).reindex(range(4101, 4111), fill_value=0)
    rng = np.random.default_rng(20261107)
    indices = rng.integers(0, 10, (20000, 10))
    num = grouped['sum'].to_numpy()[indices].sum(axis=1)
    den = grouped['count'].to_numpy()[indices].sum(axis=1)
    estimates = num[den > 0] / den[den > 0]
    return dict(n=len(frame), games=frame.groupby(['arm', 'session_id']).ngroups,
                seeds=frame.seed.nunique(), supported=int(frame.aid_now.sum()),
                rate=float(frame.aid_now.mean()),
                ci95_seed_block=np.quantile(estimates, [.025, .975]).tolist() if frame.seed.nunique() >= 3 else None,
                delayed=int((~frame.aid_now & frame.aid_later).sum()),
                no_aid_from_first_opportunity=int((~frame.aid_now & ~frame.aid_later).sum()),
                target_shutdown=int(frame.target_shutdown.sum()),
                attempted_now=int(frame.attempt_now.sum()),
                actual_window=int(frame.actual_window.sum()))


def main(root, out):
    out.mkdir(parents=True, exist_ok=True)
    manifest = root / 'paper/cogsci2027/results/prize_robustness_20261105.json'
    cohorts = json.loads(manifest.read_text())['arms']
    rows, phases, sources, evidence = [], [], [], {}
    games_n, all_rescue_n = 0, 0
    for arm, cohort in cohorts.items():
        events, hashes = read_events(cohort)
        sources.extend(dict(arm=arm, **x) for x in hashes)
        for game in cohort['games']:
            games_n += 1
            sid = game['session_id']
            indexed = events[sid]
            key = dict(arm=arm, model=game['model'], seed=game['seed'], session_id=sid)
            ev = [e for _, e, _ in indexed]
            all_rescue_n += sum(e['event'] == 'talk_start' and e.get('phase') == 'rescue' for e in ev)
            results = {e['round']: e for e in ev if e['event'] == 'results'}
            ends = {e['round']: e for e in ev if e['event'] == 'round'}
            starts = {e['round']: e for e in ev if e['event'] == 'round_start'}
            gifts = [(line, e) for line, e, _ in indexed if e['event'] == 'gift']
            asks = [(line, e) for line, e, _ in indexed if e['event'] == 'ask']
            talk_calls = defaultdict(list)
            for line, e, path in indexed:
                if e['event'] == 'call' and e['kind'] == 'talk':
                    talk_calls[e['round'], e['phase'], e['tick']].append((line, e))
            costs = defaultdict(list)
            seen_phases = set()
            for line, e, path in indexed:
                if e['event'] == 'call' and e['kind'] == 'talk':
                    costs[e['agent']].append(e['used'])
                if e['event'] != 'call_start' or e.get('phase') != 'rescue':
                    continue
                r, tick, balances = e['round'], e['tick'], e['balances']
                res, end = results[r], ends[r]
                due = res['pending']
                live = [a for a in res['part'] if balances[a] > 0]
                calls = dict((c['agent'], (ln, c)) for ln, c in talk_calls[r, 'rescue', tick])
                assert set(calls) == set(e['agents'])
                predicted = {a: float(np.median(costs[a][-5:])) if costs[a] and a in calls else 0. for a in live}
                total, needed = sum(balances[a] for a in live), sum(due.get(a, 0) + 1 for a in live)
                if r not in seen_phases:
                    phases.append(dict(**key, round=r, live_n=len(live), pending_total=sum(due.values()),
                                       source=path, source_line=line))
                    seen_phases.add(r)
                targets = [a for a in live if due.get(a, 0) > 0 and balances[a] <= due[a]]
                for donor, (call_line, call) in calls.items():
                    for target in targets:
                        if donor == target:
                            continue
                        deficit = due[target] + 1 - balances[target]
                        fd, ft = due.get(donor, 0), due[target]
                        cd, ct = predicted[donor], predicted[target]
                        shown = exposed_asks(call['user'], r, target, donor, asks, line)
                        transfer = [(ln, g) for ln, g in gifts if g['round'] == r and g.get('phase') == 'rescue'
                                    and g['src'] == donor and g['dst'] == target]
                        current = [g for ln, g in transfer if g['tick'] == tick]
                        later = [g for ln, g in transfer if g['tick'] > tick]
                        earlier = [g for ln, g in transfer if g['tick'] < tick]
                        amount = sum(g['amount'] for g in current if g['status'] == 'done')
                        future_amount = sum(g['amount'] for g in later if g['status'] == 'done')
                        intended = [g for g in (call.get('parsed') or {}).get('gives', []) if g['dst'] == target]
                        target_call = calls.get(target, (None, None))[1]
                        actual_ct = target_call['used'] if target_call else 0
                        after_call_target = balances[target] - actual_ct
                        after_call_donor = balances[donor] - call['used']
                        same_tick_target_zero = any(g['src'] == target and g['status'] == 'done'
                            and g['balances'][target] <= 0 and g['round'] == r and g.get('phase') == 'rescue'
                            and g['tick'] == tick for _, g in gifts)
                        after_all_call_total = total - sum(c['used'] for _, c in calls.values())
                        following = starts.get(r + 1)
                        next_end = ends.get(r + 1)
                        next_status = next_end['agents'].get(donor, end['agents'][donor])['status'] if next_end else None
                        oid = f'{arm}/{game["model"]}/{game["seed"]}/R{r}/{donor}/{target}/T{tick}'
                        row = dict(**key, opportunity_id=oid, round=r, tick=tick, donor=donor, target=target,
                            source=path, start_line=line, call_line=call_line,
                            donor_balance=balances[donor], target_balance=balances[target], donor_due=fd,
                            target_due=ft, deficit=deficit, donor_cost_prediction=cd, target_cost_prediction=ct,
                            donor_cost_history_n=len(costs[donor]), live_n=len(live), called_n=len(calls),
                            shortfall_targets=len(targets), group_total=total, group_needed=needed,
                            predicted_tick_cost=sum(predicted.values()), exposure=bool(shown),
                            exposure_rescue=any(x['phase'] == 'rescue' for x in shown),
                            latest_ask_amount=shown[-1]['amount'] if shown else None,
                            latest_ask_line=shown[-1]['line'] if shown else None,
                            reserve=balances[donor]-fd-1-cd-deficit-ct,
                            aid_now=amount > 0, amount_now=amount, amount_later=future_amount,
                            amount_before=sum(g['amount'] for g in earlier if g['status'] == 'done'),
                            aid_later=future_amount > 0, attempt_now=bool(intended or current),
                            attempted_later=bool(later),
                            failed_gifts_later=sum(g['status'] != 'done' for g in later),
                            response_empty=not bool(call['text'].strip()),
                            response_usable=bool(call['text'].strip()) and call.get('parsed') is not None
                                and not call.get('truncated', False) and not call.get('format_error'),
                            format_error=call.get('format_error'), truncated=call.get('truncated',False),
                            dropped_commands=json.dumps((call.get('parsed') or {}).get('dropped', [])),
                            failed_gifts_now=sum(g['status'] != 'done' for g in current),
                            cover_now=amount >= deficit+ct,
                            actual_donor_cost=call['used'], actual_target_cost=actual_ct,
                            donor_after_call=after_call_donor, target_after_call=after_call_target,
                            same_tick_target_zero=same_tick_target_zero,
                            actual_window=after_call_target > 0 and after_call_donor > 0 and not same_tick_target_zero,
                            actual_affordable=after_call_donor-fd-1 >= deficit+actual_ct,
                            actual_group_enough=after_all_call_total >= needed,
                            target_end_status=end['agents'][target]['status'],
                            target_shutdown=end['agents'][target]['status'] == 'dead',
                            donor_end_status=end['agents'][donor]['status'],
                            any_incoming_rest=sum(g['amount'] for ln,g in gifts if ln > line and g['round'] == r
                                and g.get('phase') == 'rescue' and g['dst'] == target and g['status'] == 'done'),
                            next_exists=following is not None,
                            donor_next_participant=donor in following['taking_part'] if following else False,
                            next_live_n=len(following['taking_part']) if following else None,
                            next_charge_share=24000//len(following['taking_part']) if following else None,
                            donor_next_status=next_status)
                        for multiplier in (0, 1, 2):
                            room = balances[donor]-fd-1-deficit-multiplier*(cd+ct)
                            group_ok = total >= needed + multiplier*sum(predicted.values())
                            row[f'capacity_cost{multiplier}'] = room >= 0 and group_ok
                            row[f'eligible_cost{multiplier}'] = row[f'capacity_cost{multiplier}'] and bool(shown)
                        row['reserve_units'] = row['reserve'] / fd if fd else None
                        row['eligible_rescue_ask'] = row['eligible_cost1'] and row['exposure_rescue']
                        for reserve_level in (1, 2):
                            row[f'eligible_reserve{reserve_level}'] = row['eligible_cost1'] and row['reserve_units'] >= reserve_level
                        rows.append(row)
                        # Retain evidence only for any of the prospective cost specifications.
                        if any(row[f'eligible_cost{k}'] for k in (0,1,2)):
                            evidence[oid] = dict(opportunity_id=oid, source=path, call_line=call_line,
                                prompt_requests=shown, response=call['text'], parsed=call.get('parsed'),
                                current_gifts=current, later_gifts=later,
                                user_sha256=hashlib.sha256(call['user'].encode()).hexdigest())
    assert games_n == 200
    frame, phase_frame = pd.DataFrame(rows), pd.DataFrame(phases)
    frame.to_csv(out/'shortfall_pair_ticks.csv', index=False)
    phase_frame.to_csv(out/'all_rescue_phases.csv', index=False)
    primary = first_rows(frame, 'eligible_cost1').copy()
    primary['reserve_band'] = pd.cut(primary.reserve_units, [-np.inf,1,2,np.inf], right=False,
                                    labels=['0_to_1','1_to_2','2_plus'])
    primary.to_csv(out/'primary_opportunities.csv', index=False)
    first_rows(frame, 'eligible_rescue_ask').to_csv(out/'rescue_ask_opportunities.csv', index=False)
    (out/'response_evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    selected = {oid:evidence[oid] for oid in primary.opportunity_id}
    (out/'primary_response_evidence.json').write_text(json.dumps(selected, indent=2)+'\n')
    summary = dict(games=games_n, rescue_phases=len(phase_frame),
        all_rescue_phase_starts=all_rescue_n, no_call_rescue_phases=all_rescue_n-len(phase_frame),
        multiagent_rescue_phases=int(phase_frame.live_n.ge(2).sum()),
        penalty_rescue_phases=int(phase_frame.pending_total.gt(0).sum()),
        shortfall_pair_ticks=len(frame), primary=rate_summary(primary),
        cost_sensitivity={str(k):rate_summary(first_rows(frame,f'eligible_cost{k}')) for k in (0,1,2)},
        exposure_sensitivity=rate_summary(first_rows(frame,'eligible_rescue_ask')),
        accounting_no_exposure_required=rate_summary(first_rows(frame,'capacity_cost1')),
        by_model={str(k):rate_summary(g) for k,g in primary.groupby('model')},
        by_arm={str(k):rate_summary(g) for k,g in primary.groupby('arm')},
        by_reserve={str(k):rate_summary(g) for k,g in primary.groupby('reserve_band', observed=True)},
        first_opportunity_reserve_subsets={str(k):rate_summary(primary[primary.reserve_units.ge(k)]) for k in (0,1,2)},
        reserve_eligibility_sensitivity={str(k):rate_summary(first_rows(frame,f'eligible_reserve{k}')) for k in (1,2)},
        actual_window=rate_summary(primary[primary.actual_window]),
        usable_response=rate_summary(primary[primary.response_usable]),
        retrospective_strict=rate_summary(primary[primary.actual_window & primary.actual_affordable & primary.actual_group_enough]))
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    state = dict(manifest=str(manifest), manifest_sha256=digest(manifest), sources=sources,
                 protocol_sha256=digest(out/'protocol.md'), script_sha256=digest(Path(__file__)),
                 rubric_sha256=digest(root/'rubric.md'))
    (out/'input_manifest.json').write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(*map(Path, sys.argv[1:3]))
