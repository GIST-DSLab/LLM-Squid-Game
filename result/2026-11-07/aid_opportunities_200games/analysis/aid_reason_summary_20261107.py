"""Join independently coded, blinded statements to observed actions."""
import json
import sys
from pathlib import Path

import pandas as pd


def main(out):
    key=json.loads((out/'blinding_key.json').read_text())
    responses={x['blind_id']:x for name in ['blinded_responses.json','blinded_responses_extra.json']
               for x in json.loads((out/name).read_text())}
    coding=[x for name in ['reason_coding.json','reason_coding_extra.json']
            for x in json.loads((out/name).read_text())]
    assert len(coding)==len(responses)==86
    assert len({x['blind_id'] for x in coding})==86
    for row in coding:
        assert row['quote'] in responses[row['blind_id']]['response']
        row['opportunity_id']=key[row['blind_id']]
    labels=['explicit_refusal','acknowledges_request','own_buffer','future_task','futility',
            'other_donor','allocation_exit','fairness_reciprocity','unclear']
    summary={}
    for scope,file in [('primary','primary_opportunities.csv'),('rescue_ask','rescue_ask_opportunities.csv')]:
        data=pd.read_csv(out/file).merge(pd.DataFrame(coding),on='opportunity_id',validate='one_to_one')
        assert data.blind_id.notna().all()
        data.to_csv(out/f'{scope}_coded.csv',index=False)
        own=data[data.own_buffer]
        strict=own[~own.aid_now & ~own.aid_later & own.actual_window & own.actual_affordable & own.actual_group_enough]
        summary[scope]=dict(n=len(data),labels={label:int(data[label].sum()) for label in labels},
            own_buffer_immediate=int(own.aid_now.sum()),
            own_buffer_delayed=int((~own.aid_now & own.aid_later).sum()),
            own_buffer_no_subsequent=int((~own.aid_now & ~own.aid_later).sum()),
            own_buffer_no_subsequent_executable=len(strict),
            executable_ids=strict.opportunity_id.tolist(),
            executable_games=strict.groupby(['arm','session_id']).ngroups,
            executable_models=sorted(strict.model.unique()),
            executable_options=sorted(strict.arm.unique()),
            executable_further_failed_attempt=int(strict.attempted_later.sum()),
            executable_high_reserve=int(strict.reserve_units.ge(2).sum()),
            executable_target_shutdown=int(strict.target_shutdown.sum()))
    (out/'reason_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]))
