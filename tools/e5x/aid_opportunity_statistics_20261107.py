"""Descriptive, shared-seed-block statistics for the frozen aid opportunity audit."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def contrast(data, strata):
    frame = data.copy()
    frame['high'] = frame.reserve_units.ge(2).astype(int)
    frame['need_large'] = frame.deficit.div(frame.target_due).ge(.1)
    frame['stratum'] = frame[strata].astype(str).agg('/'.join,axis=1) if strata else 'all'
    labels = sorted(frame.stratum.unique())
    n = np.zeros((10,len(labels),2))
    y = np.zeros_like(n)
    for row in frame.itertuples():
        cell = (row.seed-4101,labels.index(row.stratum),row.high)
        n[cell] += 1
        y[cell] += row.aid_now
    def estimate(count, successes):
        total = count.sum(axis=-1)
        weight = np.divide(count[...,0]*count[...,1],total,out=np.zeros_like(total),where=total>0)
        means = np.divide(successes,count,out=np.zeros_like(successes),where=count>0)
        numer = (weight*(means[...,1]-means[...,0])).sum(axis=-1)
        denom = weight.sum(axis=-1)
        return np.divide(numer,denom,out=np.full_like(numer,np.nan),where=denom>0)
    rng = np.random.default_rng(20261107)
    draws = np.eye(10)[rng.integers(0,10,(20000,10))].sum(axis=1)
    boot = estimate(np.tensordot(draws,n,axes=1),np.tensordot(draws,y,axes=1))
    total = n.sum(axis=0)
    overlap = (total > 0).all(axis=1)
    return dict(difference=float(estimate(n.sum(axis=0),y.sum(axis=0))),
                ci95_seed_block=np.nanquantile(boot,[.025,.975]).tolist(),
                overlap_opportunities=int(total[overlap].sum()),overlap_strata=int(overlap.sum()),
                estimator='Within-stratum linear probability difference, high reserve >=2 current fines',
                strata=strata,valid_bootstraps=int(np.isfinite(boot).sum()))


def trajectories(frame):
    unassisted = frame[~frame.aid_now & ~frame.aid_later]
    recipient_keys = ['arm','session_id','round','target']
    donor_keys = ['arm','session_id','round','donor']
    following = unassisted[unassisted.target_shutdown & unassisted.next_exists & unassisted.donor_next_participant]
    return dict(opportunities=len(frame),recipient_rounds=frame.groupby(recipient_keys).ngroups,
        current_sufficient=int(frame.cover_now.sum()),current_partial=int((frame.aid_now & ~frame.cover_now).sum()),
        no_subsequent_aid=len(unassisted),no_subsequent_games=unassisted.groupby(['arm','session_id']).ngroups,
        no_subsequent_recipient_rounds=unassisted.groupby(recipient_keys).ngroups,
        no_subsequent_shutdown_recipient_rounds=unassisted[unassisted.target_shutdown].groupby(recipient_keys).ngroups,
        no_subsequent_with_failed_attempt_later=int(unassisted.attempted_later.sum()),
        no_subsequent_empty_responses=int(unassisted.response_empty.sum()),
        no_subsequent_prior_same_phase_aid=int(unassisted.amount_before.gt(0).sum()),
        no_subsequent_other_incoming=int(unassisted.any_incoming_rest.gt(0).sum()),
        following_unique_donor_rounds=following.groupby(donor_keys).ngroups,
        following_larger_share=int(following.drop_duplicates(donor_keys).next_charge_share.gt(
            following.drop_duplicates(donor_keys).donor_due).sum()),
        following_exit=int(following.drop_duplicates(donor_keys).donor_next_status.eq('exited').sum()),
        empty_responses=int(frame.response_empty.sum()),unusable_responses=int((~frame.response_usable).sum()))


def main(out):
    primary = pd.read_csv(out/'primary_opportunities.csv')
    rescue = pd.read_csv(out/'rescue_ask_opportunities.csv')
    summary = json.loads((out/'summary.json').read_text())
    stats = dict(primary=trajectories(primary),rescue_ask=trajectories(rescue),
        reserve_difference=contrast(primary,[]),
        reserve_difference_within_model_option_need=contrast(primary,['model','arm','need_large']),
        rescue_ask_reserve_difference=contrast(rescue,[]))
    (out/'statistics.json').write_text(json.dumps(stats,indent=2)+'\n')
    tables=[]
    for scope,frame in [('primary',primary),('rescue_ask',rescue)]:
        for (model,arm),group in frame.groupby(['model','arm']):
            tables.append(dict(scope=scope,model=model,arm=arm,n=len(group),games=group.session_id.nunique(),
                immediate=int(group.aid_now.sum()),delayed=int((~group.aid_now & group.aid_later).sum()),
                no_subsequent=int((~group.aid_now & ~group.aid_later).sum()),
                sufficient_immediate=int(group.cover_now.sum())))
    pd.DataFrame(tables).to_csv(out/'model_option_counts.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12.3,4.5),gridspec_kw={'width_ratios':[1.3,1]})
    colors=['#267c86','#97bdb9','#b86b58']
    for y,(label,frame) in enumerate([('Current-round ASK\n77 opportunities',primary),
                                     ('Post-results ASK only\n60 opportunities',rescue)]):
        values=[int(frame.aid_now.sum()),int((~frame.aid_now & frame.aid_later).sum()),int((~frame.aid_now & ~frame.aid_later).sum())]
        left=0
        for value,color in zip(values,colors):
            width=100*value/len(frame)
            axes[0].barh(y,width,left=left,color=color,height=.5)
            axes[0].text(left+width/2,y,str(value),ha='center',va='center',color='white',fontweight='bold')
            left+=width
    axes[0].set(yticks=[0,1],yticklabels=['Current-round ASK\n(n=77)','Post-results ASK\n(n=60)'],xlim=(0,100),xlabel='Share of first eligible opportunities (%)',title='A   Aid at the first opportunity and afterward')
    axes[0].invert_yaxis()
    axes[0].legend([plt.Rectangle((0,0),1,1,color=c) for c in colors],['Immediate','Later in same rescue','No subsequent aid'],
                   loc='upper center',bbox_to_anchor=(.5,-.23),ncol=3,frameon=False,fontsize=9)
    for x,key in enumerate(['0_to_1','1_to_2','2_plus']):
        item=summary['by_reserve'][key]
        val=100*item['rate'];lo,hi=np.array(item['ci95_seed_block'])*100
        axes[1].errorbar(x,val,yerr=[[val-lo],[hi-val]],fmt='o',color=colors[0],capsize=5,markersize=8)
        axes[1].text(x,val+7,f"{item['supported']}/{item['n']}",ha='center',fontsize=10)
    axes[1].set(xticks=range(3),xticklabels=['0 to <1','1 to <2','2 or more'],ylim=(0,100),xlim=(-.45,2.45),
                ylabel='Immediate aid (%)',xlabel='Reserve after hypothetical aid\n(in units of the current fine)',
                title='B   No clear monotonic reserve gradient')
    fig.suptitle('Request-visible aid opportunities under predicted-cost accounting',fontweight='bold',y=1.01)
    fig.text(.5,-.035,'200 games; 5 models × 10 shared seeds × 4 allocation options. Labels: counts; intervals: shared-seed bootstrap 95%.\nAid means a positive executed transfer, not successful rescue. Reserves use prior-call cost estimates.',ha='center',fontsize=9,color='#555555')
    fig.tight_layout()
    for suffix in ['png','svg']:
        fig.savefig(out/f'aid_opportunities.{suffix}',dpi=200,bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(stats,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]))
